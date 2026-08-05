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

def get_next_game_message(stadiums):
    """Get next scheduled game info"""
    try:
        for days_ahead in range(1, 8):
            check_date = datetime.now(PT).date() + timedelta(days=days_ahead)
            date_str = check_date.strftime("%Y%m%d")
            
            mls_response = requests.get(
                f"{ESPN_MLS_SCOREBOARD}?dates={date_str}",
                timeout=10
            )
            mls_data = mls_response.json() if mls_response.status_code == 200 else {"events": []}
            
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
                        
                        return {
                            "away_team": away_team,
                            "home_team": home_team,
                            "time_pt": game_time_pt
                        }
        
        return None
    except Exception as e:
        print(f"Error getting next game: {str(e)}")
        return None

def main():
    """Main function - dashboard format with quick reference"""
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
        
        # Sort by time
        game_details_list.sort(key=lambda x: x["time_pt"])
        
        # Check if Leagues Cup day
        is_leagues_cup_day = any(is_leagues_cup_match(event) for event in all_events)
        
        # Determine header
        if is_leagues_cup_day:
            header = "🏆 *LEAGUES CUP - MLS vs LIGA MX*"
        else:
            header = "⚽ *MLS DAILY WEATHER REPORT*"
        
        # Build dashboard message
        if not game_details_list:
            # Off-day message (simplified)
            message = f"{header}\n\n"
            message += "📅 No games scheduled today\n\n"
            next_game = get_next_game_message(stadiums)
            if next_game:
                message += f"📍 *Next Match:* {next_game['away_team']} @ {next_game['home_team']}\n"
                message += f"📅 {next_game['time_pt'].strftime('%A, %B %d')} @ {next_game['time_pt'].strftime('%I:%M %p PT')}"
            else:
                message += "No upcoming games found"
        else:
            # Game day - Executive Dashboard
            message = f"{header}\n\n"
            message += "📊 *TODAY'S OVERVIEW*\n"
            
            # Count by risk level
            high_risk_count = sum(1 for g in game_details_list if g["risk_level"] == "HIGH RISK")
            monitor_count = sum(1 for g in game_details_list if g["risk_level"] == "MONITOR")
            clear_count = sum(1 for g in game_details_list if g["risk_level"] == "CLEAR")
            
            message += f"🎬 Games Scheduled: {len(game_details_list)}\n"
            message += f"🔴 High-Risk: {high_risk_count} games\n"
            message += f"🟡 Monitor: {monitor_count} games\n"
            message += f"🟢 Clear: {clear_count} games\n\n"
            
            # Quick Reference - Games Today
            message += "📋 *GAMES TODAY (Quick Reference)*\n"
            for i, game in enumerate(game_details_list, 1):
                risk_emoji = "🔴" if game["risk_level"] == "HIGH RISK" else "🟡" if game["risk_level"] == "MONITOR" else "🟢"
                message += f"{i}. {risk_emoji} *{game['away_team']}* @ *{game['home_team']}* | {game['time_pt'].strftime('%I:%M %p PT')}\n"
            message += "\n"
            
            # Weather Summary
            message += "⛅ *WEATHER SUMMARY*\n"
            rain_stadiums = sum(1 for g in game_details_list if g["weather"] and g["weather"].get("precipProbability", 0) >= 35)
            wind_stadiums = sum(1 for g in game_details_list if g["weather"] and g["weather"].get("windSpeed", 0) >= 20)
            
            message += f"💧 Rain expected: {rain_stadiums} stadiums\n"
            message += f"💨 Wind concerns: {wind_stadiums} stadiums (20+ mph)\n"
            message += f"🌡️ Temperature: Range varies by region\n\n"
            
            # Air Quality Alert
            message += "🌍 *AIR QUALITY ALERT*\n"
            unhealthy_aqi = sum(1 for g in game_details_list if g["aqi_data"] and g["aqi_data"].get("aqi", 0) > 100)
            if unhealthy_aqi == 0:
                message += "✅ All stadiums have healthy air quality\n\n"
            else:
                message += f"⚠️ {unhealthy_aqi} stadiums with elevated AQI\n\n"
            
            # Real-time monitoring note (informational only)
            message += "🔔 Real-time monitoring active: 10 AM - 10 PM PT"
        
        post_to_slack(message)
        print("✅ Dashboard posted")
        
    except Exception as e:
        print(f"❌ Main error: {str(e)}")
        post_to_slack(f"❌ Weather Bot Error: {str(e)}")

if __name__ == "__main__":
    main()
