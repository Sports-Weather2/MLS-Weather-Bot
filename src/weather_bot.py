import os
import requests
import json
from datetime import datetime, timedelta
import pytz

# Get environment variables
SLACK_WEBHOOK_URL = os.getenv('SLACK_WEBHOOK_URL')
OPENWEATHERMAP_API_KEY = os.getenv('OPENWEATHERMAP_API_KEY')

# ESPN API base
ESPN_MLS_SCOREBOARD = 'https://site.api.espn.com/apis/site/v2/sports/soccer/usa.1/scoreboard'

# Load stadium config
with open('config/mls_stadiums.json', 'r') as f:
    STADIUMS = json.load(f)

# Timezone for PT
PT = pytz.timezone('America/Los_Angeles')

def get_mls_games_for_date(target_date=None):
    """
    Fetch MLS games for a specific date from ESPN API.
    
    Args:
        target_date: datetime object or None for today
    
    Returns:
        List of games for that date
    """
    try:
        if target_date is None:
            target_date = datetime.now(PT).date()
        
        date_str = target_date.strftime('%Y%m%d')
        url = f"{ESPN_MLS_SCOREBOARD}?dates={date_str}"
        
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        games = data.get('events', [])
        return games
    except Exception as e:
        print(f"Error fetching games: {e}")
        return []

def get_next_scheduled_game():
    """
    Find the next scheduled MLS game starting from tomorrow.
    
    Returns:
        Dict with game info: {
            'date': 'Saturday, July 25',
            'time': '7:30 PM PT',
            'home_team': 'New York City FC',
            'away_team': 'New York Red Bulls'
        }
        or None if no games found in next 7 days
    """
    try:
        # Check next 7 days
        for days_ahead in range(1, 8):
            future_date = datetime.now(PT).date() + timedelta(days=days_ahead)
            games = get_mls_games_for_date(future_date)
            
            if games:
                # Get first game of that day
                game = games[0]
                game_date_utc = datetime.fromisoformat(game['date'].replace('Z', '+00:00'))
                game_date_pt = game_date_utc.astimezone(PT)
                
                home_team = game['competitions'][0]['home']['team']['displayName']
                away_team = game['competitions'][0]['away']['team']['displayName']
                
                formatted_date = game_date_pt.strftime('%A, %B %d')
                formatted_time = game_date_pt.strftime('%I:%M %p PT').lstrip('0')
                
                return {
                    'date': formatted_date,
                    'time': formatted_time,
                    'home_team': home_team,
                    'away_team': away_team
                }
        
        return None
    except Exception as e:
        print(f"Error getting next scheduled game: {e}")
        return None

def post_no_games_message():
    """
    Post 'No games scheduled today' message with next match date.
    """
    try:
        next_game = get_next_scheduled_game()
        
        if next_game:
            # Build message WITH next game info
            message = {
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "✅ *No games scheduled today*\n\nMLS Weather Bot is monitoring and will alert on the next game day."
                        }
                    },
                    {
                        "type": "divider"
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"🗓️ *Next Match:* {next_game['date']} at {next_game['time']}\n\n🔷 {next_game['away_team']} @ {next_game['home_team']}"
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
            }
        else:
            # Fallback: No next game found
            message = {
                "blocks": [
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
            }
        
        # Post to Slack
        response = requests.post(
            SLACK_WEBHOOK_URL,
            json=message,
            timeout=10
        )
        response.raise_for_status()
        print("✅ No-games message posted successfully with next match info")
        
    except Exception as e:
        print(f"❌ Error posting no-games message: {e}")

def post_gameday_weather_report(games):
    """
    Post comprehensive gameday weather report with all games sorted by risk.
    
    Args:
        games: List of MLS games from ESPN API
    """
    try:
        # Import weather functions
        from utils import get_weather_for_stadium, get_risk_level, get_delay_probability
        
        # Build game list with weather
        game_data = []
        
        for game in games:
            try:
                comp = game['competitions'][0]
                home_team = comp['home']['team']['displayName']
                away_team = comp['away']['team']['displayName']
                
                # Get game time
                game_date_utc = datetime.fromisoformat(game['date'].replace('Z', '+00:00'))
                game_date_pt = game_date_utc.astimezone(PT)
                game_time_pt = game_date_pt.strftime('%I:%M %p PT').lstrip('0')
                game_date_str = game_date_pt.strftime('%A, %B %d')
                
                # Find stadium
                venue_name = comp.get('venue', {}).get('fullName', 'Unknown Stadium')
                stadium_config = next((s for s in STADIUMS if s['stadium'] == venue_name), None)
                
                if not stadium_config:
                    continue
                
                # Get weather
                weather = get_weather_for_stadium(stadium_config)
                
                if not weather:
                    continue
                
                # Determine risk level
                risk_level, why_triggered = get_risk_level(weather, stadium_config)
                delay_prob = get_delay_probability(risk_level, weather)
                
                game_data.append({
                    'home': home_team,
                    'away': away_team,
                    'date': game_date_str,
                    'time': game_time_pt,
                    'weather': weather,
                    'risk_level': risk_level,
                    'why_triggered': why_triggered,
                    'delay_prob': delay_prob,
                    'team_name': stadium_config.get('team', 'Unknown')
                })
            
            except Exception as e:
                print(f"Error processing game: {e}")
                continue
        
        if not game_data:
            print("No games with valid weather data found")
            post_no_games_message()
            return
        
        # Sort by risk level (HIGH RISK first)
        risk_order = {'HIGH RISK': 0, 'MONITOR': 1, 'CLEAR': 2}
        game_data.sort(key=lambda x: risk_order.get(x['risk_level'], 3))
        
        # Build Slack message
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "⚽ *MLS Daily Weather Report*"
                }
            },
            {
                "type": "divider"
            }
        ]
        
        # Add each game
        for game in game_data:
            risk_icon = '🔴' if game['risk_level'] == 'HIGH RISK' else '🟡' if game['risk_level'] == 'MONITOR' else '🟢'
            
            weather = game['weather']
            temp = weather.get('temperature', 'N/A')
            rain = weather.get('rain_probability', 0)
            wind = weather.get('wind_speed', 0)
            conditions = weather.get('conditions', 'Unknown')
            source = weather.get('source', 'NWS')
            
            game_text = f"{risk_icon} **{game['away']} @ {game['home']}**\n"
            game_text += f"{game['date']} at {game['time']}\n\n"
            game_text += f"🌡️ {temp}°F | 💧 Rain: {rain}% | 💨 Wind: {wind} mph | {conditions}\n"
            
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
            
            blocks.append({
                "type": "divider"
            })
        
        # Add footer
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
        
        # Post to Slack
        response = requests.post(
            SLACK_WEBHOOK_URL,
            json=message,
            timeout=10
        )
        response.raise_for_status()
        print("✅ Gameday weather report posted successfully")
        
    except Exception as e:
        print(f"❌ Error posting gameday report: {e}")

def main():
    """
    Main coordinator function.
    
    If games today: Post full gameday weather report
    If no games today: Post off-day message with next match date
    """
    try:
        # Check for games today
        today_games = get_mls_games_for_date()
        
        if today_games:
            print(f"✅ Found {len(today_games)} games today")
            post_gameday_weather_report(today_games)
        else:
            print("✅ No games today - posting off-day message")
            post_no_games_message()
    
    except Exception as e:
        print(f"❌ Error in main: {e}")

if __name__ == '__main__':
    main()
