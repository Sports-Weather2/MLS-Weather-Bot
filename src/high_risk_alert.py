# high_risk_alert.py
# Updated: August 2, 2026
# Real-Time High-Risk Weather Alerts for MLS
# Posts HIGH RISK games at 10 AM on game days only
# Posts real-time alerts for delays, postponements, resumptions, suspensions with @channel tag
# DOES NOT post on off-days (off-day alerts handled by weather_bot.py at 7 AM)

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


def post_high_risk_alert(games):
    """Post HIGH RISK games or All Clear message. GAME DAY VERSION (1+ games)."""
    try:
        print(f"Line 11: Processing {len(games)} games for high risk alert")
        
        high_risk_games = []
        total_games = 0
        
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
                
                total_games += 1
                
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
        
        print(f"\nLine 13: Found {len(high_risk_games)} HIGH RISK games out of {total_games} total")
        
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
            # ALL CLEAR - GAME DAY (1+ games, but no HIGH RISK)
            alert_text = f"🟢 *All Clear*\n\nAll {total_games} games today have favorable conditions\nNo high-risk weather or air quality concerns detected"
            
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": alert_text
                }
            })
        
        # NO "Next Match" line on game days - colleagues already saw games in 7 AM dashboard
        
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


def post_weather_delay_alert(matchup, delay_reason, current_score=None, minute=None):
    """Post REAL-TIME weather delay alert with @channel tag."""
    try:
        print(f"Line 19: Posting WEATHER DELAY alert for {matchup}")
        
        # Build alert text with @channel tag
        alert_text = "@channel\n\n🚨 *WEATHER DELAY DETECTED*\n\n"
        alert_text += f"🎬 {matchup}\n"
        alert_text += f"⏸️ Kickoff DELAYED\n"
        alert_text += f"🌩️ Reason: {delay_reason}\n"
        
        if current_score and minute:
            alert_text += f"📊 Score: {current_score} | {minute}'\n"
        
        alert_text += f"⏱️ Expected update: 15-30 minutes\n\n"
        alert_text += "Status: Monitoring weather — will resume when safe"
        
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "⚽ MLS High Risk Alert",
                    "emoji": True
                }
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": alert_text
                }
            },
            {"type": "divider"},
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
        response = requests.post(SLACK_WEBHOOK_URL_HIGH_RISK, json=message, timeout=10)
        response.raise_for_status()
        print(f"Line 20: Weather delay alert posted with @channel tag")
        
    except Exception as e:
        print(f"Line 21: Error posting weather delay alert: {e}")
        import traceback
        traceback.print_exc()


def post_game_resuming_alert(matchup, current_score, minute):
    """Post REAL-TIME game resuming alert with @channel tag."""
    try:
        print(f"Line 22: Posting GAME RESUMING alert for {matchup}")
        
        # Build alert text with @channel tag
        alert_text = "@channel\n\n✅ *GAME RESUMING*\n\n"
        alert_text += f"🎬 {matchup}\n"
        alert_text += f"⚽ Play resuming now\n"
        alert_text += f"📊 Current score: {current_score} | {minute}'\n\n"
        alert_text += "Status: Game proceeding"
        
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "⚽ MLS High Risk Alert",
                    "emoji": True
                }
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": alert_text
                }
            },
            {"type": "divider"},
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
        response = requests.post(SLACK_WEBHOOK_URL_HIGH_RISK, json=message, timeout=10)
        response.raise_for_status()
        print(f"Line 23: Game resuming alert posted with @channel tag")
        
    except Exception as e:
        print(f"Line 24: Error posting game resuming alert: {e}")
        import traceback
        traceback.print_exc()


def post_game_postponed_alert(matchup, postpone_reason):
    """Post REAL-TIME game postponed alert with @channel tag."""
    try:
        print(f"Line 25: Posting GAME POSTPONED alert for {matchup}")
        
        # Build alert text with @channel tag
        alert_text = "@channel\n\n📅 *GAME POSTPONED*\n\n"
        alert_text += f"🎬 {matchup}\n"
        alert_text += f"❌ Match cancelled\n"
        alert_text += f"🌧️ Reason: {postpone_reason}\n\n"
        alert_text += "🗓️ Reschedule: TBD — League will announce new date/time"
        
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "⚽ MLS High Risk Alert",
                    "emoji": True
                }
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": alert_text
                }
            },
            {"type": "divider"},
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
        response = requests.post(SLACK_WEBHOOK_URL_HIGH_RISK, json=message, timeout=10)
        response.raise_for_status()
        print(f"Line 26: Game postponed alert posted with @channel tag")
        
    except Exception as e:
        print(f"Line 27: Error posting game postponed alert: {e}")
        import traceback
        traceback.print_exc()


def main():
    """Main function."""
    try:
        print("Line 0: Starting high_risk_alert.py")
        today_games = get_mls_games_for_date()
        
        # NO GAMES SCHEDULED - SKIP POSTING (off-day handled by weather_bot.py at 7 AM)
        if not today_games or len(today_games) == 0:
            print("Line X: No games today - skipping high risk alert")
            print("Line X: Off-day message already posted by weather_bot.py at 7 AM to #mls-gameday-weather")
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
