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
        
        if 'events' in data:
            games = data['events']
            print(f"Line 2: Found {len(games)} games on {date_str}")
            return games
        else:
            print(f"Line 3: No 'events' key in response")
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
        
        for idx, event in enumerate(events):
            try:
                if 'competitions' not in event:
                    continue
                
                comp = event['competitions'][0]
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

def post_high_risk_alert(games):
    """Post HIGH RISK games or All Clear message."""
    try:
        print(f"Line 11: Processing {len(games)} games for high risk alert")
        
        high_risk_games = []
        
        for idx, game in enumerate(games):
            try:
                print(f"Line 12.{idx}: Processing game...")
                
                if not isinstance(game, dict) or 'competitions' not in game:
                    continue
                
                comp = game['competitions'][0]
                competitors = comp.get('competitors', [])
                
                if not competitors or len(competitors) < 2:
                    continue
                
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
                except Exception as e:
                    print(f"Line 12.{idx}g: Error parsing date {date_str}: {e}")
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
                
                if risk_level == 'HIGH RISK':
                    high_risk_games.append({
                        'matchup': f"{away_team} @ {home_team}",
                        'time': game_time_pt,
                        'reason': why_triggered
                    })
                
                print(f"Line 12.{idx}z: ✅ Processed: {away_team} @ {home_team} - {risk_level}")
            
            except Exception as e:
                print(f"Line 12.{idx}ERROR: {e}")
                import traceback
                traceback.print_exc()
                continue
        
        print(f"\nLine 13: Found {len(high_risk_games)} HIGH RISK games")
        
        # Build alert message
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "⚽ MLS High Risk Alert",
                    "emoji": True
                }
            },
            {"type": "divider"}
        ]
        
        if high_risk_games:
            # HIGH RISK GAMES FOUND
            alert_text = "🔴 *HIGH RISK GAMES*\n\n"
            for game in high_risk_games:
                alert_text += f"🎬 *{game['matchup']}* ({game['time']})\n"
                alert_text += f"⚠️ {game['reason']}\n\n"
            
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": alert_text
                }
            })
        
        else:
            # ALL CLEAR
            alert_text = "🟢 *All Clear*\n\nNo high-risk conditions detected today"
            
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": alert_text
                }
            })
        
        # Add next match info
        blocks.append({"type": "divider"})
        next_game = get_next_scheduled_game()
        if next_game:
            next_match_text = f"📅 *Next Match:* {next_game['away_team']} @ {next_game['home_team']}\n{next_game['date']} @ {next_game['time']}"
        else:
            next_match_text = "📅 *Next Match:* TBD"
        
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": next_match_text
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
        print(f"Line 14: High risk alert posted to Slack")
        
    except Exception as e:
        print(f"Line 15: Error posting high risk alert: {e}")
        import traceback
        traceback.print_exc()

def main():
    """Main function."""
    try:
        print("Line 0: Starting high_risk_alert.py")
        today_games = get_mls_games_for_date()
        
        # NO GAMES SCHEDULED - DO NOT POST TO HIGH RISK ALERTS CHANNEL
        if not today_games or len(today_games) == 0:
            print("Line X: No games today - skipping high risk alert")
            return
        
        # GAMES EXIST - POST HIGH RISK ALERT
        print("Line Y: Games found - posting high risk alert")
        post_high_risk_alert(today_games)
    
    except Exception as e:
        print(f"Line Z: Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
else:
    main()
