import os
import requests
import json
from datetime import datetime
from src.utils import (
    get_nws_forecast,
    get_openweathermap_forecast,
    get_air_quality,
    get_aqi_category,
    get_stadium_coordinates,
    get_all_stadiums,
)

SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")

def get_game_schedule():
    """Fetch today's MLS game schedule from ESPN API."""
    try:
        response = requests.get(
            "https://site.api.espn.com/apis/site/v2/sports/soccer/usa.1/scoreboard",
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
        
        events = data.get("events", [])
        games_today = []
        
        for event in events:
            # Parse competitors array
            competitors = event.get("competitors", [])
            if len(competitors) >= 2:
                home_team = None
                away_team = None
                
                for competitor in competitors:
                    if competitor.get("homeAway") == "home":
                        home_team = competitor.get("team", {}).get("displayName", "Unknown")
                    elif competitor.get("homeAway") == "away":
                        away_team = competitor.get("team", {}).get("displayName", "Unknown")
                
                if home_team and away_team:
                    games_today.append({
                        "home": home_team,
                        "away": away_team,
                        "venue": event.get("venue", {}).get("fullName", "Unknown Venue")
                    })
        
        return games_today
    except Exception as e:
        print(f"Error fetching game schedule: {e}")
        return []


def get_weather_for_game(home_team):
    """Get weather data for a team's stadium."""
    stadiums = get_all_stadiums()
    
    for stadium in stadiums:
        # Try to match team name to stadium
        if home_team.lower() in stadium.get("name", "").lower() or \
           any(alias.lower() in home_team.lower() for alias in stadium.get("aliases", [])):
            
            lat = stadium.get("lat")
            lon = stadium.get("lon")
            api_source = stadium.get("api_source", "nws")
            
            try:
                # Get weather data
                if api_source == "openweathermap":
                    weather_data = get_openweathermap_forecast(lat, lon)
                else:  # nws
                    weather_data = get_nws_forecast(lat, lon)
                
                # Get air quality
                aqi = get_air_quality(lat, lon)
                if weather_data:
                    weather_data["aqi"] = aqi
                
                return weather_data, stadium.get("name")
            
            except Exception as e:
                print(f"Error getting weather for {home_team}: {e}")
                return None, None
    
    return None, None


def format_weather_blocks(game, weather_data, stadium_name):
    """Format a game's weather as Slack blocks."""
    if not weather_data:
        return {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"⚽ *{game['away']} @ {game['home']}*\n🏟️ {game['venue']}\n❌ Weather data unavailable"
            }
        }
    
    temp = weather_data.get("temp", "N/A")
    rain_prob = weather_data.get("rain_prob", 0)
    wind_speed = weather_data.get("wind_speed", 0)
    has_thunderstorm = weather_data.get("thunderstorm", False)
    aqi = weather_data.get("aqi", 0)
    
    # Determine weather emoji/status
    weather_emoji = "🟢"
    if rain_prob >= 80 or wind_speed >= 30:
        weather_emoji = "🔴"
    elif rain_prob >= 50 or wind_speed >= 20:
        weather_emoji = "🟡"
    
    thunderstorm_text = " ⚡ Thunderstorms" if has_thunderstorm else ""
    
    # Air quality text
    aqi_text = ""
    if aqi > 0:
        aqi_category = get_aqi_category(aqi)
        if aqi >= 150:
            aqi_text = f" | 💨 AQI {aqi} (🔴 {aqi_category})"
        elif aqi >= 101:
            aqi_text = f" | 💨 AQI {aqi} (🟡 {aqi_category})"
        else:
            aqi_text = f" | 💨 AQI {aqi} (🟢 {aqi_category})"
    
    weather_text = f"*Temp:* {temp}°F | *Rain:* {rain_prob}% | *Wind:* {wind_speed} mph{thunderstorm_text}{aqi_text}"
    
    return {
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"{weather_emoji} *{game['away']} @ {game['home']}*\n🏟️ {game['venue']}\n{weather_text}"
        }
    }


def send_daily_report(games, has_games):
    """Send daily weather report to Slack."""
    if not SLACK_WEBHOOK_URL:
        print("Error: SLACK_WEBHOOK_URL not set")
        return False
    
    try:
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "⚽ MLS Daily Weather Report",
                    "emoji": True
                }
            }
        ]
        
        if has_games:
            for game in games:
                weather_data, stadium_name = get_weather_for_game(game["home"])
                blocks.append(format_weather_blocks(game, weather_data, stadium_name))
                blocks.append({"type": "divider"})
        else:
            # No games today
            next_date = "Unknown"
            try:
                response = requests.get(
                    "https://site.api.espn.com/apis/site/v2/sports/soccer/usa.1/scoreboard",
                    timeout=10
                )
                data = response.json()
                events = data.get("events", [])
                if events:
                    next_event = events[0]
                    date_str = next_event.get("date", "")
                    if date_str:
                        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                        next_date = dt.strftime("%A %B %d")
            except:
                pass
            
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"No games today\nNext Check: {next_date}"
                }
            })
            blocks.append({"type": "divider"})
        
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"Updated: {datetime.now().strftime('%b %d at %I:%M %p %Z')}"
                }
            ]
        })
        
        payload = {"blocks": blocks}
        
        response = requests.post(SLACK_WEBHOOK_URL, json=payload, timeout=10)
        response.raise_for_status()
        print(f"✅ Daily weather report posted: {len(games)} games")
        return True
    
    except Exception as e:
        print(f"❌ Error posting report to Slack: {e}")
        return False


def main():
    """Main execution: fetch games and send daily weather report."""
    print("🔍 Fetching MLS game schedule...")
    
    games = get_game_schedule()
    has_games = len(games) > 0
    
    print(f"📊 Games today: {len(games)}")
    
    send_daily_report(games, has_games)


if __name__ == "__main__":
    main()
