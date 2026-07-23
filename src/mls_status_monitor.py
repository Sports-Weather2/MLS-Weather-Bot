"""
MLS game status monitor.
Runs every 10 minutes from 10 AM–10 PM PT via GitHub Actions.
Monitors game delays and posts updates to #mls-high-risk-weather Slack channel.
"""

import os
import json
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from src.utils import (
    load_stadiums,
    filter_roofed_stadiums,
    log_event
)


def get_mls_schedule() -> List[Dict]:
    """Fetch MLS schedule from ESPN/MLS API."""
    try:
        # ESPN MLS endpoint
        url = "https://site.api.espn.com/apis/site/v2/sports/soccer/mls/teams"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        teams_data = response.json()
        schedule = []
        
        for team in teams_data.get('teams', []):
            team_id = team.get('id')
            team_name = team.get('name')
            
            # Get team schedule
            schedule_url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/mls/teams/{team_id}/schedule"
            schedule_response = requests.get(schedule_url, timeout=10)
            schedule_response.raise_for_status()
            
            events = schedule_response.json().get('events', [])
            schedule.extend(events)
        
        return schedule
    except Exception as e:
        print(f"ERROR fetching MLS schedule: {e}")
        return []


def get_game_for_stadium(team_id: str, schedule: List[Dict]) -> Optional[Dict]:
    """Get today's game for a stadium."""
    today = datetime.utcnow().date()
    
    for event in schedule:
        try:
            event_date = datetime.fromisoformat(
                event.get('date', '').replace('Z', '+00:00')
            ).date()
            
            # Check if game is today or within 12 hours
            if event_date == today or (datetime.utcnow() - timedelta(hours=12)).date() <= event_date <= today:
                # Match team
                competitors = event.get('competitions', [{}])[0].get('competitors', [])
                for competitor in competitors:
                    if team_id in competitor.get('id', ''):
                        return event
        except Exception as e:
            continue
    
    return None


def check_game_status(event: Dict) -> Tuple[str, str, str]:
    """
    Check game status.
    Returns (status, status_detail, emoji).
    
    Statuses:
    - SCHEDULED: Game not started
    - LIVE: Game in progress
    - DELAYED: Game delayed
    - POSTPONED: Game postponed
    - COMPLETED: Game finished
    """
    try:
        status = event.get('status', {}).get('type', 'UNKNOWN')
        status_detail = event.get('status', {}).get('detail', '')
        
        if status == 'STATUS_SCHEDULED':
            return 'SCHEDULED', status_detail, '⏰'
        elif status == 'STATUS_IN_PROGRESS':
            return 'LIVE', status_detail, '🎮'
        elif status == 'STATUS_DELAYED':
            return 'DELAYED', status_detail, '🔴'
        elif status == 'STATUS_POSTPONED':
            return 'POSTPONED', status_detail, '❌'
        elif status == 'STATUS_FINAL':
            return 'COMPLETED', status_detail, '✅'
        else:
            return status.replace('STATUS_', ''), status_detail, '❓'
    except Exception as e:
        print(f"ERROR parsing game status: {e}")
        return 'UNKNOWN', '', '❓'


def get_game_details(event: Dict) -> Dict:
    """Extract game details."""
    try:
        competitors = event.get('competitions', [{}])[0].get('competitors', [])
        
        home_team = competitors[0] if len(competitors) > 0 else {}
        away_team = competitors[1] if len(competitors) > 1 else {}
        
        return {
            'home_team': home_team.get('team', {}).get('name', 'Unknown'),
            'away_team': away_team.get('team', {}).get('name', 'Unknown'),
            'home_score': home_team.get('score', '-'),
            'away_score': away_team.get('score', '-'),
            'start_time': event.get('date', ''),
            'venue': event.get('competitions', [{}])[0].get('venue', {}).get('fullName', 'Unknown'),
        }
    except Exception as e:
        print(f"ERROR extracting game details: {e}")
        return {}


def build_status_update(active_games: List[Dict]) -> str:
    """Build Slack status update message."""
    timestamp = datetime.utcnow().isoformat()
    
    message = f"""
📊 **MLS Game Status Update**
Timestamp: {timestamp} UTC

"""
    
    # Group by status
    delayed = [g for g in active_games if g['status'] == 'DELAYED']
    live = [g for g in active_games if g['status'] == 'LIVE']
    scheduled = [g for g in active_games if g['status'] == 'SCHEDULED']
    postponed = [g for g in active_games if g['status'] == 'POSTPONED']
    
    if delayed:
        message += "🔴 **DELAYED GAMES**\n"
        for game in delayed:
            message += f"• {game['team_name']} - {game['details']['home_team']} vs {game['details']['away_team']}\n"
            message += f"  Reason: {game['status_detail'] if game['status_detail'] else 'Weather delay'}\n"
            message += f"  Stadium: {game['details']['venue']}\n"
        message += "\n"
    
    if live:
        message += "🎮 **LIVE GAMES**\n"
        for game in live:
            message += f"• {game['team_name']} - {game['details']['home_team']} {game['details']['home_score']} vs {game['details']['away_score']} {game['details']['away_team']}\n"
        message += "\n"
    
    if scheduled:
        message += f"⏰ **UPCOMING** ({len(scheduled)} games)\n"
        for game in scheduled:
            message += f"• {game['team_name']} - {game['details']['home_team']} vs {game['details']['away_team']}\n"
        message += "\n"
    
    if postponed:
        message += "❌ **POSTPONED**\n"
        for game in postponed:
            message += f"• {game['team_name']} - {game['details']['home_team']} vs {game['details']['away_team']}\n"
        message += "\n"
    
    if not delayed and not postponed:
        message += "_No delays or postponements at this time._\n"
    
    message += "_Next update in 10 minutes_"
    
    return message


def send_to_slack(webhook_url: str, message: str) -> bool:
    """Send message to Slack webhook."""
    if not webhook_url:
        print("WARNING: SLACK_WEBHOOK_URL not configured")
        return False
    
    try:
        payload = {
            'text': message,
            'mrkdwn': True,
        }
        response = requests.post(webhook_url, json=payload, timeout=10)
        response.raise_for_status()
        print("✅ Status update sent to Slack")
        return True
    except Exception as e:
        print(f"ERROR sending to Slack: {e}")
        return False


def main():
    """Main game status monitor function."""
    print("📊 Starting MLS game status monitor...")
    
    # Load stadiums
    stadiums = filter_roofed_stadiums(load_stadiums())
    if not stadiums:
        print("ERROR: No stadiums loaded")
        return
    
    # Get MLS schedule
    schedule = get_mls_schedule()
    if not schedule:
        print("WARNING: No schedule data available")
    
    active_games = []
    
    for stadium in stadiums:
        team_id = stadium.get('team_id')
        team_name = stadium.get('team_name')
        city = stadium.get('city')
        
        try:
            # Get game for this team
            game = get_game_for_stadium(team_id, schedule)
            
            if not game:
                continue
            
            # Check game status
            status, status_detail, emoji = check_game_status(game)
            
            # Get game details
            details = get_game_details(game)
            
            # Log event
            log_event("GAME_STATUS", team_id, f"{status} - {status_detail}")
            
            # Add to active games
            active_games.append({
                'team_id': team_id,
                'team_name': team_name,
                'city': city,
                'status': status,
                'status_detail': status_detail,
                'emoji': emoji,
                'details': details,
            })
            
            print(f"{emoji} {team_name}: {status}")
        
        except Exception as e:
            print(f"ERROR processing {team_name}: {e}")
    
    # Build and send status update if there are active games
    if active_games:
        message = build_status_update(active_games)
        webhook_url = os.getenv('SLACK_WEBHOOK_URL')
        send_to_slack(webhook_url, message)
    else:
        print("✅ No active games today")
    
    print("✅ Game status monitor complete")


if __name__ == "__main__":
    main()
