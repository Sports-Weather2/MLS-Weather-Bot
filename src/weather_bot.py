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

SLACK_WEBHOOK_URL = os.getenv('SLACK_WEBHOOK_URL')
OPENWEATHERMAP_API_KEY = os.getenv('OPENWEATHERMAP_API_KEY')
ESPN_MLS_SCOREBOARD = 'https://site.api.espn.com/apis/site/v2/sports/soccer/usa.1/scoreboard'

with open('config/mls_stadiums.json', 'r') as f:
    STADIUMS = json.load(f)

PT = pytz.timezone('America/Los_Angeles')

def get_mls_games_for_date(target_date=None):
    """Fetch MLS games for a specific date using ESPN dates parameter."""
    try:
        if target_date is None:
            target_date = datetime.now(PT).date()
        
        date_str = target_date.strftime('%Y%m%d')
        url = f"{ESPN_MLS_SCOREBOARD}?dates={date_str}"
        
        print(f"Line 1: Fetching games for {date_str}: {url}")
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # ✅ KEY FIX: Extract 'events' array from response
        if 'events' in data:
            games = data['events']
            print(f"Line 2: Found {len(games)} games on {date_str}")
            return games
        else:
            print(f"Line 3: No 'events' key in response. Keys: {list(data.keys())}")
            return []
    
    except Exception as e:
        print(f"Line 4: Error fetching games: {e}")
        import traceback
        traceback.print_exc()
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
        print(f"Line 5: Fetching next 14 days: {url}")
        
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        events = data.get('events', [])
        print(f"Line 6: Total events in range: {len(events)}")
        
        if not events:
            print("Line 7: No events found")
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
                    continue
                
                home_team = home_competitor.get('team', {}).get('displayName', '')
                away_team = away_competitor.get('team', {}).get('displayName', '')
                
                if not home_team or not away_team:
                    continue
                
                date_str = event.get('date', '')
                if not date_str:
                    continue
                
                game_date_utc = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                game_date_pt = game_date_utc.astimezone(PT)
                
                formatted_date = game_date_pt.strftime('%A, %B %d')
                formatted_time = game_date_pt.strftime('%I:%M %p PT').lstrip('0')
                
                print(f"Line 8: Found valid game: {away_team} @ {home_team}")
                
                return {
                    'date': formatted_date,
                    'time': formatted_time,
                    'home_team': home_team,
                    'away_team': away_team
                }
            
            except Exception as e:
                continue
        
        print("Line 9: No valid games found after checking all events")
        return None
    
    except Exception as e:
        print(f"Line 10: Error: {e}")
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
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "⚽ MLS Daily Weather Report",
                        "emoji": True
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
                        "text": f"🗓️ *Next Match:* {next_game['date']} at {next_game['time']}\n⚽ {next_game['away_team']} @ {next_game['home_team']}"
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
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "⚽ MLS Daily Weather Report",
                        "emoji": True
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
        print("Line 11: Message posted to Slack")
        
    except Exception as e:
        print(f"Line 12: Error posting: {e}")
        import traceback
        traceback.print_exc()

def post_gameday_weather_report(games):
    """Post gameday report with weather and air quality - IMPROVED FORMATTING."""
    try:
        print(f"Line 13: Processing {len(games)} games")
        game_data = []
        
        for idx, game in enumerate(games):
            try:
                print(f"Line 14.{idx}: Processing game...")
                
                # Verify game is a dict
                if not isinstance(game, dict):
                    print(f"Line 14.{idx}a: ❌ game is {type(game)}, not dict. Value: {game}")
                    continue
                
                # Handle both 'competitions' and direct access patterns
                if 'competitions' not in game:
                    print(f"Line 14.{idx}b: No competitions key found")
                    continue
                
                comp = game['competitions'][0]
                
                # Extract home/away from competitors array
                competitors = comp.get('competitors', [])
                if not competitors or len(competitors) < 2:
                    print(f"Line 14.{idx}c: Invalid competitors array")
                    continue
                
                home_competitor = next((c for c in competitors if c.get('homeAway') == 'home'), None)
                away_competitor = next((c for c in competitors if c.get('homeAway') == 'away'), None)
                
                if not home_competitor or not away_competitor:
                    print(f"Line 14.{idx}d: Missing home or away competitor")
                    continue
                
                home_team = home_competitor.get('team', {}).get('displayName', '')
                away_team = away_competitor.get('team', {}).get('displayName', '')
                
                if not home_team or not away_team:
                    print(f"Line 14.{idx}e: Invalid team names - home: {home_team}, away: {away_team}")
                    continue
                
                date_str = game.get('date', '')
                if not date_str:
                    print(f"Line 14.{idx}f: No date found")
                    continue
                
                try:
                    game_date_utc = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                    game_date_pt = game_date_utc.astimezone(PT)
                    game_time_pt = game_date_pt.strftime('%I:%M %p PT').lstrip('0')
                    game_date_str = game_date_pt.strftime('%A, %B %d')
                except Exception as e:
                    print(f"Line 14.{idx}g: Error parsing date {date_str}: {e}")
                    continue
                
                venue_name = comp.get('venue', {}).get('fullName', 'Unknown Stadium')
                print(f"Line 14.{idx}h: Looking for stadium: {venue_name}")
                
                stadium_config = next((s for s in STADIUMS if s['stadium'] == venue_name), None)
                
                if not stadium_config:
                    print(f"Line 14.{idx}i: Stadium not found by venue name, trying team match")
                    # Try to match by team name instead
                    stadium_config = next((s for s in STADIUMS if home_team in s.get('teams', [])), None)
                    if not stadium_config:
                        print(f"Line 14.{idx}j: Could not find stadium config for {home_team}")
                        continue
                
                weather = get_weather_for_stadium(stadium_config)
                if not weather:
                    print(f"Line 14.{idx}k: No weather data for {home_team}")
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
                
                print(f"Line 14.{idx}z: ✅ Processed: {away_team} @ {home_team}")
            
            except Exception as e:
                print(f"Line 14.{idx}ERROR: {e}")
                import traceback
                traceback.print_exc()
                continue
        
        print(f"\nLine 15: Successfully processed {len(game_data)} games out of {len(games)}")
        
        if not game_data:
            print("Line 16: No valid game data, posting no games message")
            post_no_games_message()
            return
        
        risk_order = {'HIGH RISK': 0, 'MONITOR': 1, 'CLEAR': 2}
        game_data.sort(key=lambda x: risk_order.get(x['risk_level'], 3))
        
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "⚽ MLS Daily Weather Report",
                    "emoji": True
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
            
            # IMPROVED FORMATTING
            game_text = f"{risk_icon} *{game['away']} @ {game['home']}*\n"
            game_text += f"📅 {game['date']} at {game['time']}\n"
            game_text += f"\n"  # Blank line for readability
            game_text += f"🌡️ {temp}°F  |  💧 Rain: {rain}%  |  💨 Wind: {wind} mph  |  {conditions}\n"
            
            # Add air quality on separate line
            if air_quality:
                aqi = air_quality.get('aqi', 0)
                aqi_emoji = air_quality.get('emoji', '🟡')
                aqi_category = air_quality.get('category', '')
                pm25 = air_quality.get('pm25', 0)
                game_text += f"{aqi_emoji} Air Quality: AQI {aqi} ({aqi_category}) | PM2.5: {pm25}µg/m³\n"
            
            # Add why triggered and delay probability if HIGH RISK
            if game['risk_level'] == 'HIGH RISK':
                game_text += f"\n"  # Blank line for readability
                game_text += f"📋 *Why:* {game['why_triggered']}\n"
                game_text += f"🎯 *Delay Probability:* {game['delay_prob']}\n"
            
            game_text += f"\n_🌐 {source}_"
            
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": game_text
                }
            })
            
            # Add divider between games (but not after last game)
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
        print(f"Line 17: Weather report with {len(game_data)} games posted to Slack")
        
    except Exception as e:
        print(f"Line 18: Error posting report: {e}")
        import traceback
        traceback.print_exc()

def main():
    """Main function."""
    try:
        print("Line 0: Starting weather_bot.py")
        today_games = get_mls_games_for_date()
        
        if today_games:
            print(f"Line X: Found {len(today_games)} games today")
            post_gameday_weather_report(today_games)
        else:
            print("Line Y: No games today")
            post_no_games_message()
    
    except Exception as e:
        print(f"Line Z: Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
else:
    # Run when imported as module
    main()
