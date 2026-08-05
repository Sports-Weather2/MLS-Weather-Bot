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
SLACK_WEBHOOK_URL_HIGH_RISK = os.getenv("SLACK_WEBHOOK_URL_HIGH_RISK")

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
        response = requests.post(SLACK_WEBHOOK_URL_HIGH_RISK, json=payload)
        return response.status_code == 200
    except Exception as e:
        print(f"Error posting to Slack: {str(e)}")
        return False

def get_game_details(game, stadiums):
    """Extract game details"""
    try:
        competition = game.get("competitions", [{}])[0]
        competitors = competition.get("competitors", [])
        
        if len(competitors) < 2:
            return None
        
        home_team = competitors[0]["team"]["displayName"]
        away_team = competitors[1]["team"]["displayName"]
        
        game_time_str = competition.get("startDate", "")
        if not game_time_str:
            return None
        
        try:
            game_time = datetime.fromisoformat(game_time_str.replace("Z", "+00:00"))
            game_time_pt = game_time.astimezone(PT)
        except:
            return None
        
        stadium = get_stadium_by_team(stadiums, home_team)
        if not stadium:
            return None
        
        weather = get_weather_for_stadium(stadium)
        risk_level, why_triggered = get_risk_level(weather, stadium) if weather else ("UNKNOWN", "")
        
        aqi_data = get_air_quality(stadium["latitude"], stadium["longitude"])
        
        return {
            "home_team": home_team,
            "away_team": away_team,
            "time_pt": game_time_pt,
            "stadium": stadium,
            "weather": weather,
            "risk_level": risk_level,
            "why_triggered": why_triggered,
            "aqi_data": aqi_data
        }
    except Exception as e:
        print(f"Error extracting game details: {str(e)}")
        return None

def main():
    """Main function - HIGH RISK alerts only"""
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
        
        # Get game details for all games
        game_details_list = []
        for event in all_events:
            details = get_game_details(event, stadiums)
            if details:
                game_details_list.append(details)
        
        # Filter for HIGH RISK games only
        high_risk_games = [g for g in game_details_list if g["risk_level"] == "HIGH RISK"]
        
        # If no high risk games, post off-day message and exit
        if not high_risk_games:
            print("✅ No HIGH RISK games today — silent")
            return
        
        # Check if Leagues Cup day
        is_leagues_cup_day = any(is_leagues_cup_match(event) for event in all_events)
        
        # Determine header
        if is_leagues_cup_day:
            header = "🏆 *LEAGUES CUP - MLS vs LIGA MX*"
        else:
            header = "⚽ *MLS WEATHER ALERT*"
        
        # Build HIGH RISK alert message
        message = f"{header}\n\n"
        message += f"🔴 *HIGH RISK WEATHER - {len(high_risk_games)} GAME(S)*\n\n"
        
        # List each high risk game
        for i, game in enumerate(high_risk_games, 1):
            message += f"*Game {i}: {game['away_team']} @ {game['home_team']}*\n"
            message += f"⏰ {game['time_pt'].strftime('%I:%M %p PT')}\n"
            message += f"📍 {game['stadium']['stadium']}\n\n"
            
            # Weather details
            if game["weather"]:
                message += "🌦️ *Weather Conditions:*\n"
                temp = game["weather"].get("temperature", 0)
                rain = game["weather"].get("precipProbability", 0)
                wind = game["weather"].get("windSpeed", 0)
                
                if temp:
                    message += f"   🌡️ Temperature: {int(temp)}°F\n"
                if rain:
                    message += f"   💧 Rain Probability: {int(rain)}%\n"
                if wind:
                    message += f"   💨 Wind Speed: {int(wind)} mph\n"
                
                # AQI
                if game["aqi_data"]:
                    aqi = game["aqi_data"].get("aqi", 0)
                    aqi_level = game["aqi_data"].get("aqi_level", "Unknown")
                    if aqi > 100:
                        message += f"   🌍 Air Quality: {aqi_level} (AQI {aqi})\n"
                
                message += "\n"
            
            # Why triggered
            if game["why_triggered"]:
                message += f"⚠️ *Why Triggered:* {game['why_triggered']}\n\n"
        
        # Action items for high risk
        message += "✅ *ACTION REQUIRED:*\n"
        message += "• 📞 Contact venue operations immediately\n"
        message += "• 🚨 Prepare contingency plans (delay/postponement/relocation)\n"
        message += "• 📱 Alert broadcast partners and media\n"
        message += "• ⏳ Monitor real-time updates — decision window opens 2 hours before kickoff\n"
        
        post_to_slack(message)
        print(f"✅ HIGH RISK alert posted for {len(high_risk_games)} game(s)")
        
    except Exception as e:
        print(f"❌ Main error: {str(e)}")
        post_to_slack(f"❌ High Risk Alert Error: {str(e)}")

if __name__ == "__main__":
    main()
