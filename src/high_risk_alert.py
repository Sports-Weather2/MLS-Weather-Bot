#!/usr/bin/env python3
"""
MLS High-Risk Weather Alert
Posts to Slack ONLY when HIGH RISK weather conditions are detected pre-game.
Silent otherwise (no "All Clear" messages, no off-day notifications).
"""

import os
import sys
import json
import requests
import logging
from datetime import datetime, timezone

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Get current time in PT
now_utc = datetime.now(timezone.utc)
now_pt = now_utc.astimezone()
logger.info(f"Current PT time: {now_pt.strftime('%Y-%m-%d %H:%M:%S %Z')}")

# Load config
config_path = 'config/mls_stadiums.json'
if not os.path.exists(config_path):
    logger.error(f"Config not found: {config_path}")
    sys.exit(1)

with open(config_path, 'r') as f:
    config = json.load(f)

# Create stadium lookup
stadiums_by_team = {s['team']: s for s in config['stadiums']}

# Import utils
sys.path.insert(0, os.path.dirname(__file__))
from utils import get_weather_for_stadium, get_risk_level, get_air_quality

# Get secrets
slack_webhook_high_risk = os.getenv('SLACK_WEBHOOK_URL_HIGH_RISK')
if not slack_webhook_high_risk:
    logger.error("SLACK_WEBHOOK_URL_HIGH_RISK not set")
    sys.exit(1)


def fetch_mls_games():
    """Fetch MLS games for today."""
    today = now_pt.strftime('%Y%m%d')
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/usa.1/scoreboard?dates={today}"
    try:
        resp = requests.get(url, timeout=10)
        return resp.json().get('events', [])
    except Exception as e:
        logger.error(f"Failed to fetch MLS games: {e}")
        return []


def fetch_leagues_cup_games():
    """Fetch Leagues Cup games for today."""
    today = now_pt.strftime('%Y%m%d')
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/concacaf.leagues.cup/scoreboard?dates={today}"
    try:
        resp = requests.get(url, timeout=10)
        return resp.json().get('events', [])
    except Exception as e:
        logger.error(f"Failed to fetch Leagues Cup games: {e}")
        return []


def post_high_risk_alert(game_info):
    """
    Post HIGH RISK alert to Slack.
    game_info = {
        'home_team': str,
        'away_team': str,
        'stadium': str,
        'kickoff': str,
        'risk_level': str,
        'weather': dict,
        'why_triggered': str
    }
    """
    home_team = game_info['home_team']
    away_team = game_info['away_team']
    stadium = game_info['stadium']
    kickoff = game_info['kickoff']
    why_triggered = game_info['why_triggered']
    weather = game_info['weather']
    
    # Build Block Kit message
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "🚨 HIGH RISK WEATHER ALERT",
                "emoji": True
            }
        },
        {
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": f"*Away Team:*\n{away_team}"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Home Team:*\n{home_team}"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Stadium:*\n{stadium}"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Kickoff (PT):*\n{kickoff}"
                }
            ]
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Risk Factors:*\n{why_triggered}"
            }
        }
    ]
    
    # Add weather details if available
    if weather:
        weather_text = []
        if weather.get('rain_pct'):
            weather_text.append(f"💧 Rain: {weather['rain_pct']}%")
        if weather.get('wind_mph'):
            weather_text.append(f"💨 Wind: {weather['wind_mph']} mph")
        if weather.get('temp_f'):
            weather_text.append(f"🌡️ Temp: {weather['temp_f']}°F")
        if weather.get('aqi_level'):
            weather_text.append(f"🌫️ AQI: {weather['aqi_level']}")
        
        if weather_text:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "\n".join(weather_text)
                }
            })
    
    # Add footer with timestamp and @channel
    timestamp = now_pt.strftime('%I:%M %p %Z')
    blocks.append({
        "type": "context",
        "elements": [
            {
                "type": "mrkdwn",
                "text": f"<!channel> Alert sent at {timestamp}"
            }
        ]
    })
    
    # Post to Slack
    try:
        payload = {
            "blocks": blocks,
            "text": f"🚨 HIGH RISK - {away_team} vs {home_team}"
        }
        response = requests.post(slack_webhook_high_risk, json=payload, timeout=10)
        if response.status_code == 200:
            logger.info(f"✅ HIGH RISK alert posted: {away_team} vs {home_team}")
            return True
        else:
            logger.error(f"❌ Slack post failed: {response.status_code}")
            return False
    except Exception as e:
        logger.error(f"❌ Error posting to Slack: {e}")
        return False


def main():
    """Main alert logic."""
    logger.info("=" * 60)
    logger.info("MLS High-Risk Weather Alert started")
    logger.info("=" * 60)
    
    # Fetch all games
    mls_games = fetch_mls_games()
    lc_games = fetch_leagues_cup_games()
    all_games = mls_games + lc_games
    
    if not all_games:
        logger.info("✅ No games today - silent (no alert posted)")
        return
    
    logger.info(f"Found {len(all_games)} total games today")
    
    high_risk_games = []
    
    # Check each game for HIGH RISK
    for event in all_games:
        try:
            competitors = event.get('competitors', [])
            if len(competitors) < 2:
                continue
            
            home_team_name = competitors[0].get('team', {}).get('name', 'Unknown')
            away_team_name = competitors[1].get('team', {}).get('name', 'Unknown')
            
            # Find stadium config
            stadium_config = None
            for team in [home_team_name, away_team_name]:
                if team in stadiums_by_team:
                    stadium_config = stadiums_by_team[team]
                    break
            
            if not stadium_config:
                logger.warning(f"Stadium not found for {home_team_name} vs {away_team_name}")
                continue
            
            # Get weather
            weather = get_weather_for_stadium(stadium_config)
            if not weather:
                logger.warning(f"Weather fetch failed for {stadium_config['stadium_name']}")
                continue
            
            # Check risk level
            risk_level, why_triggered = get_risk_level(weather, stadium_config)
            
            # Only alert if HIGH RISK
            if risk_level == 'HIGH RISK':
                kickoff = event.get('date', 'TBD')
                # Parse and format kickoff time
                try:
                    from datetime import datetime as dt
                    kickoff_dt = dt.fromisoformat(kickoff.replace('Z', '+00:00'))
                    kickoff_pt = kickoff_dt.astimezone()
                    kickoff_str = kickoff_pt.strftime('%I:%M %p %Z')
                except:
                    kickoff_str = kickoff
                
                game_info = {
                    'home_team': home_team_name,
                    'away_team': away_team_name,
                    'stadium': stadium_config['stadium_name'],
                    'kickoff': kickoff_str,
                    'risk_level': risk_level,
                    'weather': weather,
                    'why_triggered': why_triggered
                }
                high_risk_games.append(game_info)
                logger.info(f"🚨 HIGH RISK found: {away_team_name} @ {home_team_name}")
        
        except Exception as e:
            logger.error(f"Error processing game: {e}")
            continue
    
    # Post alerts for HIGH RISK games only
    if high_risk_games:
        logger.info(f"Posting {len(high_risk_games)} HIGH RISK alert(s)")
        for game_info in high_risk_games:
            post_high_risk_alert(game_info)
    else:
        logger.info("✅ No HIGH RISK games found - silent (no alert posted)")
    
    logger.info("=" * 60)
    logger.info("MLS High-Risk Weather Alert completed")
    logger.info("=" * 60)


if __name__ == '__main__':
    main()
