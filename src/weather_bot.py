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

def load_stadiums():
    """Load stadium configuration"""
    config_path = os.path.join(os.path.dirname(__file__), "..", "config", "mls_stadiums.json")
    with open(config_path, "r") as f:
        return json.load(f)

def get_stadium_by_team(stadiums, team_name):
    """Find stadium by team name"""
    for stadium in stadiums:
        if any(team_name.lower() in t.lower() for t in stadium.get("teams", [])):
            return stadium
    return None

def is_leagues_cup_match(event):
    """Check if match is Leagues Cup"""
    if not event or "competitions" not in event:
        return False
    competition = event.get("competitions", [{}])[0]
    comp_name = competition.get("name", "").lower()
    return "leagues cup" in comp_name

def post_to_slack(message):
    """Post message to Slack"""
    payload = {"text": message}
    try:
        response = requests.post(SLACK_WEBHOOK_URL, json=payload)
        return response.status_code == 200
    except Exception as e:
        print(f"Error posting to Slack: {str(e)}")
        return False

def format_game_message(game, stadiums):
    """Format single game message with weather"""
    try:
        competition = game.get("competitions", [{}])[0]
        competitors = competition.get("competitors", [])
        
        if len(competitors) < 2:
            return None
        
        home_team = competitors[0]["team"]["displayName"]
        away_team = competitors[1]["team"]["displayName"]
        
        # Get game time
        game_time_str = competition.get("startDate", "")
        if not game_time_str:
            return None
        
        try:
            game_time = datetime.fromisoformat(game_time_str.replace("Z", "+00:00"))
            game_time_pt = game_time.astimezone(PT)
        except:
            return None
        
        # Get stadium and weather
        stadium = get_stadium_by_team(stadiums, home_team)
        if not stadium:
            return None
        
        weather = get_weather_for_stadium(stadium)
        if not weather:
            return f"⚠️ *{away_team}* @ *{home_team}* | {game_time_pt.strftime('%I:%M %p PT')}"
        
        # Get risk level
        risk_level, why_triggered = get_risk_level(weather, stadium)
        
        # Get AQI
        aqi_data = get_air_quality(stadium["latitude"], stadium["longitude"])
        aqi_emoji = ""
        if aqi_data and aqi_data.get("aqi_level"):
            aqi_category = get_aqi_category(aqi_data["aqi"])
            aqi_emoji = f" {aqi_category['emoji']}"
        
        # Risk indicator
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

def get_next_game_message(stadiums):
    """Get next scheduled game info"""
    try:
        # Check next 7 days
        for days_ahead in range(1, 8):
            check_date = datetime.now(PT).date() + timedelta(days=days_ahead)
            date_str = check_date.strftime("%Y%m%d")
            
            # Fetch MLS games
            mls_response = requests.get(
                f"{ESPN_MLS_SCOREBOARD}?dates={date_str}",
                timeout=10
            )
            mls_data = mls_response.json() if mls_response.status_code == 200 else {"events": []}
            
            # Fetch Leagues Cup games
            lc_response = requests.get(
                f"{ESPN_LEAGUES_CUP_SCOREBOARD}?dates={date_str}",
                timeout=10
            )
            lc_data = lc_response.json() if lc_response.status_code == 200 else {"events": []}
            
            all_events = mls_data.get("events", []) + lc_data.get("events", [])
            
            if all_events:
                event = all_events[0]
                competition = event.get("competitions", [{}])[0]
                competitors = competition.get("competitors", [])
                
                if len(competitors) >= 2:
                    home_team = competitors[0]["team"]["displayName"]
                    away_team = competitors[1]["team"]["displayName"]
                    
                    game_time_str = competition.get("startDate", "")
                    if game_time_str:
                        game_time = datetime.fromisoformat(game_time_str.replace("Z", "+00:00"))
                        game_time_pt = game_time.astimezone(PT)
                        
                        return f"📍 *Next Match:* {away_team} @ {home_team}\n📅 {game_time_pt.strftime('%A, %B %d')} @ {game_time_pt.strftime('%I:%M %p PT')}"
        
        return None
    except Exception as e:
        print(f"Error getting next game: {str(e)}")
        return None

def main():
    """Main function"""
    try:
        today = datetime.now(PT).date()
        date_str = today.strftime("%Y%m%d")
        
        stadiums = load_stadiums()
        
        # Fetch MLS games
        try:
            mls_response = requests.get(
                f"{ESPN_MLS_SCOREBOARD}?dates={date_str}",
                timeout=10
            )
            mls_data = mls_response.json() if mls_response.status_code == 200 else {"events": []}
        except Exception as e:
            print(f"MLS API Error: {str(e)}")
            mls_data = {"events": []}
        
        # Fetch Leagues Cup games
        try:
            lc_response = requests.get(
                f"{ESPN_LEAGUES_CUP_SCOREBOARD}?dates={date_str}",
                timeout=10
            )
            lc_data = lc_response.json() if lc_response.status_code == 200 else {"events": []}
        except Exception as e:
            print(f"Leagues Cup API Error: {str(e)}")
            lc_data = {"events": []}
        
        # Combine events
        all_events = mls_data.get("events", []) + lc_data.get("events", [])
        
        # Check if Leagues Cup day
        is_leagues_cup_day = any(is_leagues_cup_match(event) for event in all_events)
        
        header = "🏆 LEAGUES CUP - MLS vs LIGA MX" if is_leagues_cup_day else "⚽ *MLS WEATHER REPORT*"
        
        # Build message
        if not all_events:
            # Off-day message
            message = f"{header}\n\n📅 No games scheduled today\n\n"
            next_game = get_next_game_message(stadiums)
            if next_game:
                message += next_game
            else:
                message += "No upcoming games found"
        else:
            message = f"{header}\n\n"
            
            game_count = len(all_events)
            if game_count == 1:
                # Single game
                game_line = format_game_message(all_events[0], stadiums)
                if game_line:
                    message += f"🎬 *Match:* {game_line}\n"
            else:
                # Multiple games
                message += f"📊 *Games Today ({game_count}):*\n"
                for i, game in enumerate(all_events, 1):
                    game_line = format_game_message(game, stadiums)
                    if game_line:
                        message += f"{i}. {game_line}\n"
            
            # Monitoring note
            message += f"\n⏰ *Monitoring:* 10 AM - 10 PM PT"
        
        post_to_slack(message)
        print("✅ Message posted")
        
    except Exception as e:
        print(f"❌ Main error: {str(e)}")
        post_to_slack(f"❌ Weather Bot Error: {str(e)}")

if __name__ == "__main__":
    main()
