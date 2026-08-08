#!/usr/bin/env python3
"""
MLS Real-Time Game Status Monitor
Monitors MLS + Leagues Cup games for delays, postponements, suspensions, and resumptions.
Includes automatic game detection to skip monitoring on off-days/off-season.
"""

import os
import sys
import json
import requests
import logging
from datetime import datetime, timezone
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Get timezone-aware current time (UTC)
now_utc = datetime.now(timezone.utc)
# Convert to PT
now_pt = now_utc.astimezone()
logger.info(f"Current PT time: {now_pt.strftime('%Y-%m-%d %H:%M:%S %Z')}")

# Load configuration
config_path = 'config/mls_stadiums.json'
if not os.path.exists(config_path):
    logger.error(f"Config file not found: {config_path}")
    sys.exit(1)

with open(config_path, 'r') as f:
    config = json.load(f)

# Create stadium lookup - map each team name to stadium config
stadiums = {}
for stadium in config:
    for team_name in stadium.get('teams', []):
        stadiums[team_name] = stadium

# Get secrets
slack_bot_token = os.getenv('SLACK_BOT_TOKEN')
slack_webhook_high_risk = os.getenv('SLACK_WEBHOOK_URL_HIGH_RISK')

if not slack_bot_token or not slack_webhook_high_risk:
    logger.error("Missing required Slack credentials")
    sys.exit(1)

slack_client = WebClient(token=slack_bot_token)

# Load game state cache
game_states_file = 'mls_game_states.json'
if os.path.exists(game_states_file):
    with open(game_states_file, 'r') as f:
        game_states = json.load(f)
else:
    game_states = {}


def check_games_today():
    """
    Query ESPN MLS + Leagues Cup APIs to see if games are scheduled today.
    Returns True if games exist, False otherwise.
    Also handles off-season/World Cup break auto-skip.
    """
    today = now_pt.strftime('%Y%m%d')
    
    # Check MLS
    mls_url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/usa.1/scoreboard?dates={today}"
    try:
        mls_resp = requests.get(mls_url, timeout=10)
        mls_events = mls_resp.json().get('events', [])
    except Exception as e:
        logger.warning(f"MLS API error: {e}")
        mls_events = []
    
    # Check Leagues Cup
    leagues_cup_url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/concacaf.leagues.cup/scoreboard?dates={today}"
    try:
        lc_resp = requests.get(leagues_cup_url, timeout=10)
        lc_events = lc_resp.json().get('events', [])
    except Exception as e:
        logger.warning(f"Leagues Cup API error: {e}")
        lc_events = []
    
    total_games = len(mls_events) + len(lc_events)
    return total_games > 0


def fetch_game_data():
    """Fetch current MLS + Leagues Cup game data from ESPN."""
    today = now_pt.strftime('%Y%m%d')
    games = []
    
    # MLS games
    mls_url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/usa.1/scoreboard?dates={today}"
    try:
        mls_resp = requests.get(mls_url, timeout=10)
        mls_events = mls_resp.json().get('events', [])
        games.extend([{'event': e, 'league': 'MLS'} for e in mls_events])
        logger.info(f"✅ Fetched {len(mls_events)} MLS games")
    except Exception as e:
        logger.error(f"MLS API error: {e}")
    
    # Leagues Cup games
    lc_url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/concacaf.leagues.cup/scoreboard?dates={today}"
    try:
        lc_resp = requests.get(lc_url, timeout=10)
        lc_events = lc_resp.json().get('events', [])
        games.extend([{'event': e, 'league': 'Leagues Cup'} for e in lc_events])
        logger.info(f"✅ Fetched {len(lc_events)} Leagues Cup games")
    except Exception as e:
        logger.error(f"Leagues Cup API error: {e}")
    
    return games


def get_game_state(event):
    """Extract game state (SCHEDULED, INPROGRESS, FINAL, POSTPONED, SUSPENDED)."""
    try:
        status_obj = event.get('status', {})
        if isinstance(status_obj, dict):
            status = status_obj.get('type', 'UNKNOWN')
        else:
            status = str(status_obj)
        
        status = status.upper() if status else 'UNKNOWN'
        
        # Map ESPN status to our categories
        status_map = {
            'PRE': 'SCHEDULED',
            'LIVE': 'INPROGRESS',
            'FINAL': 'FINAL',
            'POSTPONED': 'POSTPONED',
            'SUSPENDED': 'SUSPENDED'
        }
        
        return status_map.get(status, status)
    except Exception as e:
        logger.warning(f"Error getting game state: {e}")
        return 'UNKNOWN'


def get_stadium_name(team_name):
    """Look up stadium name from config."""
    if team_name in stadiums:
        return stadiums[team_name].get('stadium', 'Unknown Stadium')
    return 'Unknown Stadium'


def get_score_and_clock(event):
    """Extract current score and clock from event."""
    try:
        competitors = event.get('competitors', [])
        if len(competitors) >= 2:
            home_score = competitors[0].get('score', 0)
            away_score = competitors[1].get('score', 0)
            score = f"{away_score} - {home_score}"
        else:
            score = "N/A"
        
        # Get current time/status
        status_detail = event.get('status', {}).get('detail', '')
        clock = status_detail if status_detail else 'In Progress'
        
        return score, clock
    except Exception as e:
        logger.warning(f"Could not extract score/clock: {e}")
        return '', ''


def post_to_slack(message_data):
    """
    Post structured message to Slack using Block Kit format.
    message_data = {
        'game_id': str,
        'home_team': str,
        'away_team': str,
        'stadium': str,
        'alert_type': 'DELAY' | 'POSTPONEMENT' | 'SUSPENDED' | 'RESUMED',
        'reason': str (optional),
        'score': str (optional),
        'clock': str (optional)
    }
    """
    alert_type = message_data.get('alert_type', '')
    home_team = message_data.get('home_team', 'Unknown')
    away_team = message_data.get('away_team', 'Unknown')
    stadium = message_data.get('stadium', 'Unknown Stadium')
    reason = message_data.get('reason', '')
    score = message_data.get('score', '')
    clock = message_data.get('clock', '')
    
    # Determine emoji and mention type
    if alert_type == 'DELAY':
        emoji = '⏱️'
        mention = '<!channel>'
        title = f'{emoji} GAME DELAY'
    elif alert_type == 'POSTPONEMENT':
        emoji = '❌'
        mention = '<!channel>'
        title = f'{emoji} GAME POSTPONED'
    elif alert_type == 'SUSPENDED':
        emoji = '⛈️'
        mention = '<!channel>'
        title = f'{emoji} GAME SUSPENDED'
    elif alert_type == 'RESUMED':
        emoji = '▶️'
        mention = '<!here>'
        title = f'{emoji} GAME RESUMING'
    else:
        emoji = '⚠️'
        mention = ''
        title = f'{emoji} GAME STATUS UPDATE'
    
    # Build Block Kit message
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": title,
                "emoji": True
            }
        },
        {
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": f"*Game:*\n{away_team} vs {home_team}"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Status:*\n{alert_type}"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Venue:*\n{stadium}"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Stadium Type:*\n🌞 Open Air"
                }
            ]
        }
    ]
    
    # Add score if available
    if score:
        blocks.append({
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": f"*Score:*\n{score}"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Clock:*\n{clock}"
                }
            ]
        })
    
    # Add reason if available
    if reason:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Reason:*\n{reason}"
            }
        })
    
    # Add footer with timestamp and mention
    timestamp = now_pt.strftime('%I:%M %p %Z')
    blocks.append({
        "type": "context",
        "elements": [
            {
                "type": "mrkdwn",
                "text": f"{mention} Alert sent at {timestamp}"
            }
        ]
    })
    
    # Post via webhook
    try:
        payload = {
            "blocks": blocks,
            "text": f"{title} - {away_team} vs {home_team}"
        }
        response = requests.post(slack_webhook_high_risk, json=payload, timeout=10)
        if response.status_code == 200:
            logger.info(f"✅ Slack message posted: {alert_type}")
        else:
            logger.error(f"❌ Slack post failed: {response.status_code} {response.text}")
    except Exception as e:
        logger.error(f"❌ Error posting to Slack: {e}")


def main():
    """Main monitoring loop."""
    logger.info("=" * 60)
    logger.info("Real-Time Delay Monitor started")
    logger.info("=" * 60)
    
    # Step 1: Check if games exist today
    if not check_games_today():
        logger.info("⏭️ No games today - skipping delay monitor")
        return
    
    logger.info("✅ Games found today - proceeding with monitoring")
    
    # Step 2: Fetch current game data
    games = fetch_game_data()
    if not games:
        logger.info("No games fetched")
        return
    
    logger.info(f"Monitoring {len(games)} games for status changes")
    
    # Step 3: Check each game for status changes
    for game_data in games:
        event = game_data['event']
        league = game_data['league']
        
        game_id = event.get('id')
        competitors = event.get('competitors', [])
        
        # Extract team names safely
        if len(competitors) >= 2:
            home_team = competitors[0].get('team', {}).get('name', 'Unknown')
            away_team = competitors[1].get('team', {}).get('name', 'Unknown')
        else:
            home_team = 'Unknown'
            away_team = 'Unknown'
        
        current_state = get_game_state(event)
        previous_state = game_states.get(game_id, 'UNKNOWN')
        
        stadium = get_stadium_name(home_team)
        score, clock = get_score_and_clock(event)
        
        logger.info(f"Game {game_id}: {away_team} @ {home_team} ({league}) - State: {current_state} (was {previous_state})")
        
        # Detect state change
        if previous_state == 'UNKNOWN':
            # First time seeing this game
            game_states[game_id] = current_state
        elif current_state != previous_state:
            # State changed
            logger.warning(f"🔔 Status change detected: {previous_state} → {current_state}")
            
            if current_state == 'POSTPONED' and previous_state in ['SCHEDULED', 'INPROGRESS']:
                message_data = {
                    'game_id': game_id,
                    'home_team': home_team,
                    'away_team': away_team,
                    'stadium': stadium,
                    'alert_type': 'POSTPONEMENT',
                    'reason': event.get('status', {}).get('details', 'Weather conditions'),
                    'score': score,
                    'clock': clock
                }
                post_to_slack(message_data)
            
            elif current_state == 'SUSPENDED' and previous_state == 'INPROGRESS':
                message_data = {
                    'game_id': game_id,
                    'home_team': home_team,
                    'away_team': away_team,
                    'stadium': stadium,
                    'alert_type': 'SUSPENDED',
                    'reason': event.get('status', {}).get('details', 'Game suspended'),
                    'score': score,
                    'clock': clock
                }
                post_to_slack(message_data)
            
            elif current_state == 'INPROGRESS' and previous_state == 'SUSPENDED':
                message_data = {
                    'game_id': game_id,
                    'home_team': home_team,
                    'away_team': away_team,
                    'stadium': stadium,
                    'alert_type': 'RESUMED',
                    'score': score,
                    'clock': clock
                }
                post_to_slack(message_data)
            
            # Update state
            game_states[game_id] = current_state
    
    # Step 4: Save updated game states
    try:
        with open(game_states_file, 'w') as f:
            json.dump(game_states, f, indent=2)
        logger.info(f"✅ Game states saved ({len(game_states)} total)")
    except Exception as e:
        logger.error(f"❌ Failed to save game states: {e}")
    
    logger.info("✅ Real-Time Delay Monitor completed")


if __name__ == '__main__':
    main()
