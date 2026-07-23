"""
MLS Game Status Monitor - Real-time game delay detection.
Runs every 10 minutes from 10:00 AM - 10:00 PM PT via GitHub Actions.
Monitors live games for weather delays and postponements.
Sends alerts to #mls-high-risk-alerts Slack channel.
"""

import os
import json
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from src.utils import (
    load_stadiums,
    log_event
)


def get_mls_games_today() -> List[Dict]:
    """
    Fetch MLS games for today from ESPN API.
    Returns list of games with details.
    """
    try:
        # Get today's date in YYYYMMDD format
        today = datetime.utcnow().strftime("%Y%m%d")
        
        # ESPN MLS scoreboard endpoint
        url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/usa.1/scoreboard?dates={today}"
        
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        events = data.get('events', [])
        
        return events
    except Exception as e:
        print(f"ERROR fetching MLS games: {e}")
        return []


def parse_game_status(event: Dict) -> Dict:
    """
    Parse ESPN event data to extract game status.
    
    Returns dict with:
    - game_id
    - home_team
    - away_team
    - status (scheduled, in_progress, final, postponed)
    - start_time
    - current_score
    - delay_info (if applicable)
    """
    try:
        status_type = event.get('status', {}).get('type', 'STATUS_UNKNOWN')
        status_desc = event.get('status', {}).get('description', '')
        
        competitors = event.get('competitors', [])
        home_team = competitors[0].get('team', {}).get('displayName', 'Unknown') if len(competitors) > 0 else 'Unknown'
        away_team = competitors[1].get('team', {}).get('displayName', 'Unknown') if len(competitors) > 1 else 'Unknown'
        
        home_score = competitors[0].get('score', 0) if len(competitors) > 0 else 0
        away_score = competitors[1].get('score', 0) if len(competitors) > 1 else 0
        
        return {
            'game_id': event.get('id'),
            'home_team': home_team,
            'away_team': away_team,
            'status_type': status_type,
            'status_desc': status_desc,
            'start_time': event.get('date'),
            'home_score': home_score,
            'away_score': away_score,
            'note': event.get('note', ''),  # May contain delay info
        }
    except Exception as e:
        print(f"ERROR parsing game status: {e}")
        return {}


def detect_weather_delay(game: Dict) -> Tuple[bool, str]:
    """
    Detect if game is delayed due to weather.
    
    Returns (is_delayed, delay_reason).
    """
    status_desc = game.get('status_desc', '').lower()
    note = game.get('note', '').lower()
    
    # Check for weather delay keywords
    weather_keywords = ['weather', 'rain', 'lightning', 'thunderstorm', 'wind', 'delay']
    
    combined_text = f"{status_desc} {note}"
    
    is_weather_delay = any(keyword in combined_text for keyword in weather_keywords)
    
    if is_weather_delay:
        return True, f"Weather delay detected: {game.get('status_desc', 'Unknown reason')}"
    
    return False, ""


def detect_postponement(game: Dict) -> Tuple[bool, str]:
    """
    Detect if game is postponed or cancelled.
    
    Returns (is_postponed, reason).
    """
    status_type = game.get('status_type', '').lower()
    status_desc = game.get('status_desc', '').lower()
    note = game.get('note', '').lower()
    
    postpone_keywords = ['postponed', 'cancelled', 'canceled', 'ppd']
    
    combined_text = f"{status_type} {status_desc} {note}"
    
    is_postponed = any(keyword in combined_text for keyword in postpone_keywords)
    
    if is_postponed:
        return True, f"Game postponed: {game.get('status_desc', 'Unknown reason')}"
    
    return False, ""


def build_delay_alert_message(game: Dict, delay_reason: str) -> str:
    """Build Slack alert for a game delay."""
    return f"""
🚨 **WEATHER DELAY DETECTED**
Game: ⚾ {game['away_team']} @ {game['home_team']}
Status: {game['status_desc']}
Score: {game['away_team']} {game['away_score']}, {game['home_team']} {game['home_score']}
Reason: {delay_reason}
Time: {datetime.utcnow().isoformat()} UTC
@channel Alert sent
"""


def build_postponement_alert_message(game: Dict, postpone_reason: str) -> str:
    """Build Slack alert for a postponement."""
    return f"""
📅 **GAME POSTPONED**
Game: ⚾ {game['away_team']} @ {game['home_team']}
Status: {game['status_desc']}
Reason: {postpone_reason}
Time: {datetime.utcnow().isoformat()} UTC
@channel Alert sent
"""


def build_resumption_alert_message(game: Dict) -> str:
    """Build Slack alert for game resumption."""
    return f"""
✅ **GAME RESUMING**
Game: ⚾ {game['away_team']} @ {game['home_team']}
Status: In Progress
Score: {game['away_team']} {game['away_score']}, {game['home_team']} {game['home_score']}
Time: {datetime.utcnow().isoformat()} UTC
"""


def send_to_slack(webhook_url: str, message: str) -> bool:
    """Send message to Slack webhook."""
    if not webhook_url:
        print("WARNING: SLACK_WEBHOOK_URL_HIGH_RISK not configured")
        return False
    
    try:
        payload = {
            'text': message,
            'mrkdwn': True,
        }
        response = requests.post(webhook_url, json=payload, timeout=10)
        response.raise_for_status()
        print("✅ Alert sent to Slack")
        return True
    except Exception as e:
        print(f"ERROR sending to Slack: {e}")
        return False


def main():
    """Main game status monitor function."""
    print("📊 Starting MLS Game Status Monitor...")
    
    # Fetch today's games
    games = get_mls_games_today()
    
    if not games:
        print("✅ No MLS games today")
        return
    
    print(f"📋 Found {len(games)} game(s) today")
    
    webhook_url = os.getenv('SLACK_WEBHOOK_URL_HIGH_RISK')
    
    # Process each game
    for event in games:
        game = parse_game_status(event)
        
        if not game:
            continue
        
        game_id = game.get('game_id')
        matchup = f"{game['away_team']} @ {game['home_team']}"
        status = game.get('status_desc', 'Unknown')
        
        print(f"\n📌 {matchup}")
        print(f"   Status: {status}")
        
        # Check for postponement (highest priority)
        is_postponed, postpone_reason = detect_postponement(game)
        if is_postponed:
            print(f"   ⚠️  POSTPONED: {postpone_reason}")
            log_event("GAME_POSTPONED", game_id, postpone_reason)
            message = build_postponement_alert_message(game, postpone_reason)
            send_to_slack(webhook_url, message)
            continue
        
        # Check for weather delay
        is_delayed, delay_reason = detect_weather_delay(game)
        if is_delayed:
            print(f"   ⚠️  DELAYED: {delay_reason}")
            log_event("WEATHER_DELAY", game_id, delay_reason)
            message = build_delay_alert_message(game, delay_reason)
            send_to_slack(webhook_url, message)
            continue
        
        # Check if game is in progress (may be resuming from delay)
        if 'in progress' in status.lower() or 'live' in status.lower():
            print(f"   ✅ In Progress")
            log_event("GAME_IN_PROGRESS", game_id, status)
            # Optional: Send resumption alert
            # message = build_resumption_alert_message(game)
            # send_to_slack(webhook_url, message)
        
        # Check if game is final
        elif 'final' in status.lower():
            print(f"   ✅ Final")
            log_event("GAME_FINAL", game_id, status)
        
        # Game scheduled
        elif 'scheduled' in status.lower():
            print(f"   ⏰ Scheduled")
            log_event("GAME_SCHEDULED", game_id, status)
        
        else:
            print(f"   ℹ️  {status}")
    
    print("\n✅ Game Status Monitor complete")


if __name__ == "__main__":
    main()
