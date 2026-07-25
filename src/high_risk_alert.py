import os
import requests
import json
from datetime import datetime, timedelta
import pytz
from src.utils import (
    get_weather_for_stadium,
    get_risk_level,
    get_delay_probability,
    get_air_quality,
    get_aqi_category,
)

SLACK_WEBHOOK_URL_HIGH_RISK = os.getenv('SLACK_WEBHOOK_URL_HIGH_RISK')
ESPN_MLS_SCOREBOARD = 'https://site.api.espn.com/apis/site/v2/sports/soccer/usa.1/scoreboard'

with open('config/mls_stadiums.json', 'r') as f:
    STADIUMS = json.load(f)

PT = pytz.timezone('America/Los_Angeles')

def get_mls_games_for_date(target_date=None):
    """Fetch MLS games for a specific date."""
    try:
        if target_date is None:
            target_date = datetime.now(PT).date()
        
        date_str = target_date.strftime('%Y%m%d')
        url = f"{ESPN_MLS_SCOREBOARD}?dates={date_str}"
        
        print(f"Fetching games for {date_str}: {url}")
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        games = data.get('events', [])
        print(f"Found {len(games)} games on {date_str}")
        return games
    
    except Exception as e:
        print(f"Error fetching games: {e}")
        import traceback
        traceback.print_exc()
        return []

def post_high_risk_alert(high_risk_games):
    """Post ONE consolidated message with all HIGH RISK games."""
    try:
        if not high_risk_games:
            # Post "All Clear" message
            blocks = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "⚽ MLS High-Risk Weather Alert",
                        "emoji": True
                    }
                },
                {"type": "divider"},
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "✅ *System Status: Active & Monitoring*\n\n🟢 All Clear — No high-risk games today"
                    }
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f"Updated: {datetime.now(PT).strftime('%b %d at %I:%M %p PT')}"
                        }
                    ]
                }
            ]
        else:
            # Post consolidated HIGH RISK message with all games
            blocks = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "⚽ MLS High-Risk Weather Alert",
                        "emoji": True
                    }
                },
                {"type": "divider"},
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"🔴 *{len(high_risk_games)} High-Risk Game(s) Detected*\n\nImmediate attention may be required for scheduling and EPG adjustments."
                    }
                },
                {"type": "divider"}
            ]
            
            # Add all high-risk games in ONE section with compact format
            games_text = ""
            for idx, game in enumerate(high_risk_games):
                # Compact format for multiple games
                games_text += f"🔴 *{game['away']} @ {game['home']}*\n"
                games_text += f"   📅 {game['date']} at {game['time']}\n"
                games_text += f"   📋 {game['why_triggered']}\n"
                games_text += f"   🎯 Delay Prob: {game['delay_prob']}\n"
                
                # Add air quality if available
                if game['air_quality']:
                    aqi = game['air_quality'].get('aqi', 0)
                    emoji = game['air_quality'].get('emoji', '🟡')
                    category = game['air_quality'].get('category', '')
                    games_text += f"   {emoji} AQI {aqi} ({category})\n"
                
                # Weather summary
                weather = game['weather']
                temp = weather.get('temperature', 'N/A')
                rain = weather.get('rain_probability', 0)
                wind = weather.get('wind_speed', 0)
                conditions = weather.get('conditions', 'Unknown')
                games_text += f"   🌡️ {temp}°F | 💧 {rain}% | 💨 {wind} mph | {conditions}\n"
                
                # Add space between games
                if idx < len(high_risk_games) - 1:
                    games_text += "\n"
            
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": games_text
                }
            })
            
            blocks.append({"type": "divider"})
            blocks.append({
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"Updated: {datetime.now(PT).strftime('%b %d at %I:%M %p PT')}"
                    }
                ]
            })
        
        message = {"blocks": blocks}
        response = requests.post(SLACK_WEBHOOK_URL_HIGH_RISK, json=message, timeout=10)
        response.raise_for_status()
        print(f"✅ High-risk alert posted to Slack ({len(high_risk_games)} games)")
        
    except Exception as e:
        print(f"❌ Error posting alert: {e}")
        import traceback
        traceback.print_exc()

def main():
    """Main function - check for HIGH RISK games and post ONE consolidated message."""
    try:
        print("Starting high_risk_alert.py")
        
        today_games = get_mls_games_for_date()
        if not today_games:
            print("No games today")
            post_high_risk_alert([])
            return
        
        high_risk_games = []
        
        for idx, game in enumerate(today_games):
            try:
                if not isinstance(game, dict) or 'competitions' not in game:
                    continue
                
                comp = game['competitions'][0]
                competitors = comp.get('competitors', [])
                
                home_competitor = next((c for c in competitors if c.get('homeAway') == 'home'), None)
                away_competitor = next((c for c in competitors if c.get('homeAway') == 'away'), None)
                
                if not home_competitor or not away_competitor:
                    continue
                
                home_team = home_competitor.get('team', {}).get('displayName', '')
                away_team = away_competitor.get('team', {}).get('displayName', '')
                
                if not home_team or not away_team:
                    continue
                
                date_str = game.get('date', '')
                if not date_str:
                    continue
                
                try:
                    game_date_utc = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                    game_date_pt = game_date_utc.astimezone(PT)
                    game_time_pt = game_date_pt.strftime('%I:%M %p PT').lstrip('0')
                    game_date_str = game_date_pt.strftime('%A, %B %d')
                except Exception as e:
                    continue
                
                venue_name = comp.get('venue', {}).get('fullName', 'Unknown Stadium')
                stadium_config = next((s for s in STADIUMS if s['stadium'] == venue_name), None)
                
                if not stadium_config:
                    stadium_config = next((s for s in STADIUMS if home_team in s.get('teams', [])), None)
                    if not stadium_config:
                        continue
                
                weather = get_weather_for_stadium(stadium_config)
                if not weather:
                    continue
                
                risk_level, why_triggered = get_risk_level(weather, stadium_config)
                
                # Only add if HIGH RISK
                if risk_level != 'HIGH RISK':
                    continue
                
                delay_prob = get_delay_probability(risk_level, weather)
                
                # Get air quality
                lat = stadium_config.get('latitude')
                lon = stadium_config.get('longitude')
                air_quality_data = get_air_quality(lat, lon)
                
                air_quality_info = {}
                if air_quality_data:
                    aqi_cat = get_aqi_category(air_quality_data['aqi'])
                    air_quality_info = {
                        'aqi': air_quality_data['aqi'],
                        'category': aqi_cat['category'],
                        'emoji': aqi_cat['emoji'],
                        'pm25': air_quality_data['pm25'],
                    }
                
                high_risk_games.append({
                    'home': home_team,
                    'away': away_team,
                    'date': game_date_str,
                    'time': game_time_pt,
                    'weather': weather,
                    'air_quality': air_quality_info,
                    'risk_level': risk_level,
                    'why_triggered': why_triggered,
                    'delay_prob': delay_prob
                })
            
            except Exception as e:
                print(f"Error processing game {idx}: {e}")
                continue
        
        print(f"Found {len(high_risk_games)} HIGH RISK games")
        
        # Post ONE consolidated message
        post_high_risk_alert(high_risk_games)
    
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
else:
    main()
