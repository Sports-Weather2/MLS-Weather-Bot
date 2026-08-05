import os
import json
import requests
from datetime import datetime, timedelta
import pytz
from src.utils import get_weather_for_stadium, get_risk_level, get_air_quality, get_aqi_category

# ESPN API endpoints
ESPN_MLS_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/soccer/usa.1/scoreboard"
ESPN_LEAGUES_CUP_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/soccer/concacaf.leagues.cup/scoreboard"

# Slack webhook
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")

# PT timezone
PT = pytz.timezone("America/Los_Angeles")

def is_leagues_cup_match(competition):
    """Check if a match is a Leagues Cup game"""
    if not competition:
        return False
    comp_name = competition.get("name", "").lower()
    comp_uid = competition.get("uid", "").lower()
    return "leagues cup" in comp_name or "usa.3" in comp_uid or "concacaf.leagues.cup" in comp_uid

def load_stadiums():
    """Load stadium configuration from mls_stadiums.json"""
    config_path = os.path.join(os.path.dirname(__file__), "..", "config", "mls_stadiums.json")
    with open(config_path, "r") as f:
        return json.load(f)

def get_stadium_by_team(stadiums, team_name):
    """Find stadium configuration by team name"""
    for stadium in stadiums:
        if any(team_name.lower() in t.lower() for t in stadium.get("teams", [])):
            return stadium
    return None

def post_to_slack(message):
    """Post message to Slack"""
    payload = {"text": message}
    response = requests.post(SLACK_WEBHOOK_URL, json=payload)
    return response.status_code == 200

def format_game_message(game, stadiums):
    """Format a single game with weather and risk info"""
    try:
        # Extract game info
        competition = game.get("competitions", [{}])[0]
        competitors = competition.get("competitors", [])
        
        home_team = competitors[0]["team"]["displayName"] if len(competitors) > 0 else "Unknown"
        away_team = competitors[1]["team"]["displayName"] if len(competitors) > 1 else "Unknown"
        
        # Get time
        game_time_str = competition.get("startDate", "")
        if game_time_str:
            game_time = datetime.fromisoformat(game_time_str.replace("Z", "+00:00"))
            game_time_pt = game_time.astimezone(PT)
        else:
            return None
        
        # Get stadium
        stadium = get_stadium_by_team(stadiums, home_team)
        if not stadium:
            return None
        
        # Get weather
        weather = get_weather_for_stadium(stadium)
        if not weather:
            return f"⚠️ *{away_team}* @ *{home_team}* | {game_time_pt.strftime('%I:%M %p PT')} | ⚠️ Weather unavailable"
        
        # Get risk level
        risk_level, why_triggered = get_risk_level(weather, stadium)
        
        # Get AQI
        aqi_data = get_air_quality(stadium["latitude"], stadium["longitude"])
        aqi_emoji = ""
        if aqi_data and aqi_data.get("aqi_level"):
            aqi_category = get_aqi_category(aqi_data["aqi"])
            aqi_emoji = f" {aqi_category['emoji']}"
        
        # Format risk indicator
        risk_emoji = "🟢" if risk_level == "CLEAR" else "🟡" if risk_level == "MONITOR" else "🔴"
        
        # Weather summary
        weather_summary = ""
        if weather.get("temperature"):
            weather_summary += f"{int(weather['temperature'])}°F"
        if weather.get("precipProbability"):
            weather_summary += f" | {int(weather['precipProbability'])}% rain"
        if weather.get("windSpeed"):
            weather_summary += f" | {int(weather['windSpeed'])} mph wind"
        
        return f"{risk_emoji} *{away_team}* @ *{home_team}* | {game_time_pt.strftime('%I:%M %p PT')} | {weather_summary}{aqi_emoji}"
    
    except Exception as e:
        print(f"Error formatting game: {str(e)}")
        return None

def main():
    """Main function - fetch games and post to Slack"""
    try:
        # Get today's date
        today = datetime.now(PT).date()
        date_str = today.strftime("%Y%m%d")
        
        # Load stadiums
        stadiums = load_stadiums()
        
        # Fetch MLS games
        try:
            mls_response = requests.get(
                f"{ESPN_MLS_SCOREBOARD}?dates={date_str}",
                timeout=10
            )
            mls_response.raise_for_status()
            mls_data = mls_response.json()
        except Exception as e:
            print(f"MLS API Error: {str(e)}")
            mls_data = {"events": []}
        
        # Fetch Leagues Cup games
        try:
            lc_response = requests.get(
                f"{ESPN_LEAGUES_CUP_SCOREBOARD}?dates={date_str}",
                timeout=10
            )
            lc_response.raise_for_status()
            lc_data = lc_response.json()
        except Exception as e:
            print(f"Leagues Cup API Error: {str(e)}")
            lc_data = {"events": []}
        
        # Combine all events
        all_events = mls_data.get("events", []) + lc_data.get("events", [])
        
        # Filter for gameday events only (status not "Scheduled")
        games = []
        for event in all_events:
            competition = event.get("competitions", [{}])[0]
            status = competition.get("status", {}).get("type", "")
            # Include scheduled games and any with weather implications
            if status in ["scheduled", "inprogress", "delayed"] or not status:
                games.append(event)
        
        # Determine header
        is_leagues_cup_day = any(
            is_leagues_cup_match(event.get("competitions", [{}])[0])
            for event in games
        )
        
        header = "🏆 LEAGUES CUP - MLS vs LIGA MX" if is_leagues_cup_day else "⚽ *MLS WEATHER REPORT*"
        
        # Build message
        if not games:
            # Off-day message
            next_game = get_next_game(stadiums)
            message = f"{header}\n\n"
            message += "📅 No games scheduled today\n\n"
            if next_game:
                message += f"📍 *Next Match:* {next_game['away_team']} @ {next_game['home_team']}\n"
                message += f"📅 {next_game['date_str']} @ {next_game['time_str']}"
            else:
                message += "No upcoming games found"
        else:
            # Game day message
            message = f"{header}\n\n"
            
            game_count = len(games)
            if game_count == 1:
                # Single game format
                game_line = format_game_message(games[0], stadiums)
                if game_line:
                    message += f"🎬 *Match:* {game_line}\n"
            else:
                # Multiple games format
                message += f"📊 *Games Today ({game_count}):*\n"
                for i, game in enumerate(games, 1):
                    game_line = format_game_message(game, stadiums)
                    if game_line:
                        message += f"{i}. {game_line}\n"
            
            # Add monitoring note
            message += f"\n⏰ *Monitoring:* 10 AM - 10 PM PT"
        
        # Post to Slack
        post_to_slack(message)
        print(f"✅ Message posted to Slack")
        
    except Exception as e:
        print(f"❌ Error in main: {str(e)}")
        post_to_slack(f"❌ Weather Bot Error: {str(e)}")

def get_next_game(stadiums):
    """Get next scheduled game (stub for now)"""
    # This would query ESPN for next game
    # For now, return None to avoid errors
    return None

if __name__ == "__main__":
    main()
