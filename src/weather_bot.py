import os
import requests
import json
from datetime import datetime, timedelta
import pytz

SLACK_WEBHOOK_URL = os.getenv('SLACK_WEBHOOK_URL')
OPENWEATHERMAP_API_KEY = os.getenv('OPENWEATHERMAP_API_KEY')
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
        
        print(f"Fetching games from: {url}")
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        games = data.get('events', [])
        print(f"Found {len(games)} games on {date_str}")
        return games
    except Exception as e:
        print(f"Error fetching games: {e}")
        return []

def get_next_scheduled_game():
    """Find next scheduled game using competitors array."""
    try:
        tomorrow = datetime.now(PT).date() + timedelta(days=1)
        end_date = tomorrow + timedelta(days=13)
        
        start_str = tomorrow.strftime('%Y%m%d')
        end_str = end_date.strftime('%Y%m%d')
        date_range = f"{start_str}-{end_str}"
        
        url = f"{ESPN_MLS_SCOREBOARD}?dates={date_range}"
        print(f"Fetching next 14 days: {url}")
        
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        events = data.get('events', [])
        print(f"Total events in range: {len(events)}")
        
        if not events:
            print("No events found")
            return None
        
        # Iterate through events to find first valid game
        for idx, event in enumerate(events):
            try:
                if 'competitions' not in event:
                    continue
                
                comp = event['competitions'][0]
                
                # Extract home/away from competitors array
                competitors = comp.get('competitors', [])
                
                home_competitor = next((c for c in competitors if c.get('homeAway') == 'home'), None)
                away_competitor = next((c for c in competitors if c.get('homeAway') == 'away'), None)
                
                if not home_competitor or not away_competitor:
                    print(f"Event {idx}: Missing home or away competitor")
                    continue
                
                home_team = home_competitor.get('team', {}).get('displayName', '')
                away_team = away_competitor.get('team', {}).get('displayName', '')
                
                if not home_team or not away_team:
                    print(f"Event {idx}: Invalid team names")
                    continue
                
                date_str = event.get('date', '')
                if not date_str:
                    print(f"Event {idx}: No date")
                    continue
                
                game_date_utc = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                game_date_pt = game_date_utc.astimezone(PT)
                
                formatted_date = game_date_pt.strftime('%A, %B %d')
                formatted_time = game_date_pt.strftime('%I:%M %p PT').lstrip('0')
                
                print(f"✅ Found valid game: {away_team} @ {home_team}")
                
                return {
                    'date': formatted_date,
                    'time': formatted_time,
                    'home_team': home_team,
                    'away_team': away_team
                }
            
            except Exception as e:
                print(f"Event {idx} error: {e}")
                continue
        
        print("❌ No valid games found after checking all events")
        return None
    
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return None

def post_no_games_message():
    """Post no games message with next match if available."""
    try:
        next_game = get_next_scheduled_game()
        
        if next_game:
            blocks = [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "⚽ *MLS Daily Weather Report*"
                    }
                },
                {"type": "divider"},
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "✅ *No games scheduled today*\n\nMLS Weather Bot is monitoring and will alert on the next game day."
                    }
                },
                {"type": "divider"},
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"🗓️ *Next Match:* {next_game['date']} at {next_game['time']}\n\n⚽ {next_game['away_team']} @ {next_game['home_team']}"
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
            blocks = [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "⚽ *MLS Daily Weather Report*"
                    }
                },
                {"type": "divider"},
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "✅ *No games scheduled today*\n\nMLS Weather Bot is monitoring and will alert on the next game day."
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
        
        message = {"blocks": blocks}
        response = requests.post(SLACK_WEBHOOK_URL, json=message, timeout=10)
        response.raise_for_status()
        print("✅ Message posted to Slack")
        
    except Exception as e:
        print(f"Error posting: {e}")

def post_gameday_weather_report(games):
    """Post gameday report with weather and air quality."""
    try:
        from utils import get_weather_for_stadium, get_risk_level, get_delay_probability, get_air_quality, get_aqi_category
        
        game_data = []
        
        for game in games:
            try:
                comp = game['competitions'][0]
                
                # Extract home/away from competitors array
                competitors = comp.get('competitors', [])
                home_competitor = next((c for c in competitors if c.get('homeAway') == 'home'), None)
                away_competitor = next((c for c in competitors if c.get('homeAway') == 'away'), None)
                
                if not home_competitor or not away_competitor:
                    continue
                
                home_team = home_competitor.get('team', {}).get('displayName', '')
                away_team = away_competitor.get('team', {}).get('displayName', '')
                
                if not home_team or not away_team:
                    continue
                
                game_date_utc = datetime.fromisoformat(game['date'].replace('Z', '+00:00'))
                game_date_pt = game_date_utc.astimezone(PT)
                game_time_pt = game_date_pt.strftime('%I:%M %p PT').lstrip('0')
                game_date_str = game_date_pt.strftime('%A, %B %d')
                
                venue_name = comp.get('venue', {}).get('fullName', 'Unknown Stadium')
                stadium_config = next((s for s in STADIUMS if s['stadium'] == venue_name), None)
                
                if not stadium_config:
                    continue
                
                weather = get_weather_for_stadium(stadium_config)
                if not weather:
                    continue
                
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
                        'pm10': air_quality_data['pm10'],
                        'level': aqi_cat['level']
                    }
                
                risk_level, why_triggered = get_risk_level(weather, stadium_config)
                delay_prob = get_delay_probability(risk_level, weather)
                
                game_data.append({
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
                print(f"Error: {e}")
                continue
        
        if not game_data:
            post_no_games_message()
            return
        
        risk_order = {'HIGH RISK': 0, 'MONITOR': 1, 'CLEAR': 2}
        game_data.sort(key=lambda x: risk_order.get(x['risk_level'], 3))
        
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "⚽ *MLS Daily Weather Report*"
                }
            },
            {"type": "divider"}
        ]
        
        for idx, game in enumerate(game_data):
            risk_icon = '🔴' if game['risk_level'] == 'HIGH RISK' else '🟡' if game['risk_level'] == 'MONITOR' else '🟢'
            weather = game['weather']
            air_quality = game['air_quality']
            temp = weather.get('temperature', 'N/A')
            rain = weather.get('rain_probability', 0)
            wind = weather.get('wind_speed', 0)
            conditions = weather.get('conditions', 'Unknown')
            source = weather.get('source', 'NWS')
            
            game_text = f"{risk_icon} **{game['away']} @ {game['home']}**\n"
            game_text += f"{game['date']} at {game['time']}\n\n"
            game_text += f"🌡️ {temp}°F | 💧 Rain: {rain}% | 💨 Wind: {wind} mph | {conditions}\n"
            
            # Add air quality if available
            if air_quality:
                aqi = air_quality.get('aqi', 0)
                aqi_emoji = air_quality.get('emoji', '🟡')
                aqi_category = air_quality.get('category', '')
                pm25 = air_quality.get('pm25', 0)
                game_text += f"{aqi_emoji} Air Quality: AQI {aqi} ({aqi_category}) | PM2.5: {pm25}µg/m³\n"
            
            if game['risk_level'] == 'HIGH RISK':
                game_text += f"📋 *Why:* {game['why_triggered']}\n"
                game_text += f"🎯 *Delay Probability:* {game['delay_prob']}\n"
            
            game_text += f"_🌐 {source}_"
            
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": game_text
                }
            })
            
            if idx < len(game_data) - 1:
                blocks.append({"type": "divider"})
        
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
        response = requests.post(SLACK_WEBHOOK_URL, json=message, timeout=10)
        response.raise_for_status()
        print("✅ Posted")
        
    except Exception as e:
        print(f"Error: {e}")

def main():
    """Main function."""
    try:
        today_games = get_mls_games_for_date()
        
        if today_games:
            print(f"Found {len(today_games)} games today")
            post_gameday_weather_report(today_games)
        else:
            print("No games today")
            post_no_games_message()
    
    except Exception as e:
        print(f"Error: {e}")

if __name__ == '__main__':
    main()
