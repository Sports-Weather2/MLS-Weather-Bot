import os
import requests
import json
from datetime import datetime, timedelta
import pytz

SLACK_WEBHOOK_URL_HIGH_RISK = os.getenv('SLACK_WEBHOOK_URL_HIGH_RISK')

with open('config/mls_stadiums.json', 'r') as f:
    STADIUMS = json.load(f)

PT = pytz.timezone('America/Los_Angeles')

def get_mls_games_for_date(target_date=None):
    """Fetch MLS games for a specific date."""
    try:
        if target_date is None:
            target_date = datetime.now(PT).date()
        
        date_str = target_date.strftime('%Y%m%d')
        url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/usa.1/scoreboard?dates={date_str}"
        
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        games = data.get('events', [])
        print(f"Found {len(games)} games on {date_str}")
        return games
    
    except Exception as e:
        print(f"Error fetching games: {e}")
        return []

def post_high_risk_alert(high_risk_games, all_clear=False):
    """Post high-risk weather alerts to Slack."""
    try:
        from src.utils import get_weather_for_stadium, get_air_quality, get_aqi_category
        
        now_pt = datetime.now(PT)
        
        if all_clear:
            # Post "All Clear - No Games" message
            next_check = (datetime.now(PT).date() + timedelta(days=1)).strftime('%A, %B %d, %Y')
            blocks = [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "⚽ *MLS High-Risk Weather Alert*"
                    }
                },
                {"type": "divider"},
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "✅ *System Status:* Active & Monitoring"
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "🟢 *Games Scheduled:* No games today"
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"📅 *Next Check:* {next_check}"
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "ℹ️ Real-time monitoring will resume during next scheduled games."
                    }
                },
                {"type": "divider"},
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f"Updated: {now_pt.strftime('%b %d at %I:%M %p PT')}"
                        }
                    ]
                }
            ]
            
            message = {"blocks": blocks}
            response = requests.post(SLACK_WEBHOOK_URL_HIGH_RISK, json=message, timeout=10)
            response.raise_for_status()
            print("✅ All Clear message posted")
            return
        
        if not high_risk_games:
            print("No high-risk games to post")
            return
        
        # Build blocks for each high-risk game
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "⚽ *MLS High-Risk Weather Alert*"
                }
            },
            {"type": "divider"}
        ]
        
        for idx, game in enumerate(high_risk_games):
            try:
                away_team = game.get('away_team', 'Unknown')
                home_team = game.get('home_team', 'Unknown')
                date_str = game.get('date', 'N/A')
                time_str = game.get('time', 'N/A')
                weather = game.get('weather', {})
                air_quality = game.get('air_quality', {})
                risk_level = game.get('risk_level', 'UNKNOWN')
                why_triggered = game.get('why_triggered', 'Unknown condition')
                delay_prob = game.get('delay_prob', 'Unknown')
                
                # Build weather string
                temp = weather.get('temperature', 'N/A')
                rain = weather.get('rain_probability', 0)
                wind = weather.get('wind_speed', 0)
                conditions = weather.get('conditions', 'Unknown')
                
                weather_str = f"🌡️ {temp}°F | 💧 Rain: {rain}% | 💨 Wind: {wind} mph | {conditions}"
                
                # Add air quality if available
                aqi = air_quality.get('aqi', 0)
                aqi_category = air_quality.get('category', '')
                pm25 = air_quality.get('pm25', 0)
                
                if aqi > 0:
                    aqi_emoji = air_quality.get('emoji', '🟡')
                    weather_str += f"\n💨 Air Quality: {aqi_emoji} AQI {aqi} ({aqi_category}) | PM2.5: {pm25}µg/m³"
                
                # Build game block
                game_text = f"🔴 *{away_team} @ {home_team}*\n"
                game_text += f"{date_str} at {time_str}\n\n"
                game_text += f"{weather_str}\n\n"
                game_text += f"📋 *Why Triggered:* {why_triggered}\n"
                game_text += f"🎯 *Delay Probability:* {delay_prob}"
                
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": game_text
                    }
                })
                
                if idx < len(high_risk_games) - 1:
                    blocks.append({"type": "divider"})
            
            except Exception as e:
                print(f"Error processing game: {e}")
                continue
        
        # Add timestamp
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"Updated: {now_pt.strftime('%b %d at %I:%M %p PT')}"
                }
            ]
        })
        
        message = {"blocks": blocks}
        response = requests.post(SLACK_WEBHOOK_URL_HIGH_RISK, json=message, timeout=10)
        response.raise_for_status()
        print(f"✅ Posted {len(high_risk_games)} high-risk game(s)")
    
    except Exception as e:
        print(f"Error posting alert: {e}")

def check_high_risk_games():
    """Check today's games for high-risk weather and air quality."""
    try:
        from src.utils import get_weather_for_stadium, get_risk_level, get_delay_probability, get_air_quality, get_aqi_category
        
        print("🔍 Starting MLS high-risk weather alert check...")
        
        games = get_mls_games_for_date()
        
        if not games:
            print("❌ No games scheduled today - skipping alert")
            post_high_risk_alert([], all_clear=True)
            return
        
        high_risk_games = []
        
        for game in games:
            try:
                # Parse game info
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
                
                # Get game time
                game_date_utc = datetime.fromisoformat(game['date'].replace('Z', '+00:00'))
                game_date_pt = game_date_utc.astimezone(PT)
                game_time_pt = game_date_pt.strftime('%I:%M %p PT').lstrip('0')
                game_date_str = game_date_pt.strftime('%A, %B %d')
                
                # Get stadium
                venue_name = comp.get('venue', {}).get('fullName', 'Unknown Stadium')
                stadium_config = next((s for s in STADIUMS if s['stadium'] == venue_name), None)
                
                if not stadium_config:
                    continue
                
                # Get weather
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
                
                # Determine risk level (weather only for now)
                risk_level, why_triggered = get_risk_level(weather, stadium_config)
                delay_prob = get_delay_probability(risk_level, weather)
                
                # Check if HIGH RISK from air quality
                if air_quality_info and air_quality_info['aqi'] >= 150:
                    if risk_level != 'HIGH RISK':
                        risk_level = 'HIGH RISK'
                        why_triggered = f"Air quality concern - AQI {air_quality_info['aqi']} ({air_quality_info['category']})"
                        delay_prob = '🟠 HIGH — Air quality delay risk'
                    else:
                        why_triggered += f" + Air quality AQI {air_quality_info['aqi']}"
                
                # Only add if HIGH RISK
                if risk_level == 'HIGH RISK':
                    high_risk_games.append({
                        'home_team': home_team,
                        'away_team': away_team,
                        'date': game_date_str,
                        'time': game_time_pt,
                        'weather': weather,
                        'air_quality': air_quality_info,
                        'risk_level': risk_level,
                        'why_triggered': why_triggered,
                        'delay_prob': delay_prob
                    })
                    print(f"🚨 HIGH RISK: {away_team} @ {home_team}")
            
            except Exception as e:
                print(f"Error processing game: {e}")
                continue
        
        # Post results
        if high_risk_games:
            print(f"📢 Found {len(high_risk_games)} high-risk game(s)")
            post_high_risk_alert(high_risk_games)
        else:
            print("✅ No high-risk games - posting All Clear")
            post_high_risk_alert([], all_clear=True)
    
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

def main():
    """Main function."""
    try:
        check_high_risk_games()
    except Exception as e:
        print(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
