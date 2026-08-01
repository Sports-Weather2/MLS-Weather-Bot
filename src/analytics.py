import os
import json
import requests
from datetime import datetime, timedelta
import pytz
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

PT = pytz.timezone('America/Los_Angeles')
ANALYTICS_FILE = 'ANALYTICS.md'

# Slack setup
SLACK_TOKEN = os.getenv('SLACK_BOT_TOKEN')
HIGH_RISK_CHANNEL = 'mls-high-risk-alerts'
GAMEDAY_CHANNEL = 'mls-gameday-weather'

# ESPN API
ESPN_MLS_SCOREBOARD = 'https://site.api.espn.com/apis/site/v2/sports/soccer/usa.1/scoreboard'

def get_slack_client():
    """Initialize Slack client."""
    try:
        return WebClient(token=SLACK_TOKEN)
    except Exception as e:
        print(f"Error initializing Slack client: {e}")
        return None

def get_yesterday_messages(client, channel_name):
    """Get Slack messages from yesterday."""
    try:
        yesterday = datetime.now(PT) - timedelta(days=1)
        yesterday_start = yesterday.replace(hour=0, minute=0, second=0).timestamp()
        yesterday_end = yesterday.replace(hour=23, minute=59, second=59).timestamp()
        
        response = client.conversations_list(types='public')
        channel_id = None
        for channel in response['channels']:
            if channel['name'] == channel_name:
                channel_id = channel['id']
                break
        
        if not channel_id:
            print(f"Channel {channel_name} not found")
            return []
        
        messages_response = client.conversations_history(
            channel=channel_id,
            oldest=str(yesterday_start),
            latest=str(yesterday_end)
        )
        
        return messages_response.get('messages', [])
    
    except SlackApiError as e:
        print(f"Error fetching Slack messages: {e}")
        return []

def parse_high_risk_alerts(messages):
    """Parse HIGH RISK alert messages to extract game count."""
    high_risk_count = 0
    high_risk_games = []
    
    for message in messages:
        text = message.get('text', '')
        
        # Look for "X High-Risk Game(s) Detected" pattern
        if 'High-Risk Game' in text:
            try:
                # Extract number from "🔴 *5 High-Risk Game(s) Detected*"
                import re
                match = re.search(r'(\d+)\s+High-Risk Game', text)
                if match:
                    high_risk_count = int(match.group(1))
            except Exception as e:
                print(f"Error parsing high-risk count: {e}")
        
        # Look for "All Clear" message
        if 'All Clear' in text:
            high_risk_count = 0
    
    return high_risk_count

def parse_daily_report(messages):
    """Parse daily weather report for game counts."""
    games_scheduled = 0
    high_risk = 0
    monitor = 0
    clear = 0
    
    for message in messages:
        text = message.get('text', '')
        
        if 'Games Scheduled:' in text:
            try:
                import re
                # Extract from "🎮 *Games Scheduled:* 14"
                match = re.search(r'Games Scheduled:\*\s*(\d+)', text)
                if match:
                    games_scheduled = int(match.group(1))
                
                # Extract high-risk count
                match = re.search(r'High-Risk:\*\s*(\d+)', text)
                if match:
                    high_risk = int(match.group(1))
                
                # Extract monitor count
                match = re.search(r'Monitor:\*\s*(\d+)', text)
                if match:
                    monitor = int(match.group(1))
                
                # Extract clear count
                match = re.search(r'Clear:\*\s*(\d+)', text)
                if match:
                    clear = int(match.group(1))
            except Exception as e:
                print(f"Error parsing daily report: {e}")
    
    return {
        'games_scheduled': games_scheduled,
        'high_risk': high_risk,
        'monitor': monitor,
        'clear': clear
    }

def get_actual_delays_from_espn():
    """Check ESPN API for games that were delayed/postponed yesterday."""
    try:
        yesterday = datetime.now(PT) - timedelta(days=1)
        date_str = yesterday.strftime('%Y%m%d')
        
        url = f"{ESPN_MLS_SCOREBOARD}?dates={date_str}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        events = data.get('events', [])
        actual_delays = 0
        postponements = 0
        
        for event in events:
            try:
                status = event.get('status', {})
                status_type = status.get('type', '')
                status_detail = status.get('detail', '')
                
                # Check if game was delayed
                if 'delayed' in status_type.lower() or 'delayed' in status_detail.lower():
                    actual_delays += 1
                
                # Check if game was postponed
                if 'postpone' in status_type.lower() or 'postpone' in status_detail.lower():
                    postponements += 1
            
            except Exception as e:
                continue
        
        return {
            'actual_delays': actual_delays,
            'postponements': postponements
        }
    
    except Exception as e:
        print(f"Error fetching ESPN data: {e}")
        return {
            'actual_delays': 0,
            'postponements': 0
        }

def calculate_accuracy(high_risk_alerts, actual_delays):
    """Calculate prediction accuracy."""
    if actual_delays == 0:
        return 0.0 if high_risk_alerts == 0 else None  # N/A if alerts but no delays
    
    # Simplified: assume high-risk alerts correspond to actual delays
    correctly_predicted = min(high_risk_alerts, actual_delays)
    accuracy = (correctly_predicted / actual_delays) * 100
    
    return accuracy

def update_analytics_file(daily_report, high_risk_alerts, actual_data):
    """Update ANALYTICS.md with latest data."""
    try:
        now = datetime.now(PT)
        yesterday = now - timedelta(days=1)
        
        games_scheduled = daily_report.get('games_scheduled', 0)
        high_risk = daily_report.get('high_risk', 0)
        monitor = daily_report.get('monitor', 0)
        clear = daily_report.get('clear', 0)
        
        actual_delays = actual_data.get('actual_delays', 0)
        postponements = actual_data.get('postponements', 0)
        
        accuracy = calculate_accuracy(high_risk_alerts, actual_delays)
        
        # Read existing file
        with open(ANALYTICS_FILE, 'r') as f:
            content = f.read()
        
        # Update key metrics
        content = content.replace(
            '| 📅 Games Monitored | 14 |',
            f'| 📅 Games Monitored | {games_scheduled} |'
        )
        
        content = content.replace(
            '| 🚨 High-Risk Alerts | 1 |',
            f'| 🚨 High-Risk Alerts | {high_risk} |'
        )
        
        content = content.replace(
            '| 🟡 Monitor Alerts | 1 |',
            f'| 🟡 Monitor Alerts | {monitor} |'
        )
        
        content = content.replace(
            '| ⏸️ Actual Delays | 0 |',
            f'| ⏸️ Actual Delays | {actual_delays} |'
        )
        
        content = content.replace(
            '| 📅 Actual Postponements | 0 |',
            f'| 📅 Actual Postponements | {postponements} |'
        )
        
        # Update accuracy
        if accuracy is not None:
            accuracy_str = f'**{accuracy:.1f}%**' if accuracy >= 0 else '**N/A**'
        else:
            accuracy_str = '**N/A**'
        
        content = content.replace(
            '| **Accuracy Rate** | **N/A** |',
            f'| **Accuracy Rate** | {accuracy_str} |'
        )
        
        # Update recent activity section
        yesterday_str = yesterday.strftime('%B %d, %Y')
        recent_activity = f"""### Yesterday ({yesterday_str})

- 🎮 Games Scheduled: {games_scheduled}
- 📊 Alerts Sent: {high_risk + monitor}
  - 🚨 High-Risk: {high_risk}
  - 🟡 Monitor: {monitor}
- ⏸️ Delays Detected: {actual_delays}
- 📅 Postponements: {postponements}"""
        
        # Replace yesterday's section
        import re
        pattern = r'### Yesterday \([^)]+\).*?(?=### Previous Day|---)'
        content = re.sub(pattern, recent_activity + '\n\n', content, flags=re.DOTALL)
        
        # Update timestamp
        timestamp = now.strftime('%B %d, %Y %I:%M %p PT')
        content = content.replace(
            '_Last updated:',
            f'_Last updated: {timestamp}\n_Next review: {(now + timedelta(days=1)).strftime("%B %d, %Y")}_'
        )
        
        # Write updated file
        with open(ANALYTICS_FILE, 'w') as f:
            f.write(content)
        
        print(f"✅ Analytics updated successfully")
        print(f"   Games: {games_scheduled} | High-Risk: {high_risk} | Actual Delays: {actual_delays}")
        print(f"   Accuracy: {accuracy_str}")
        
    except Exception as e:
        print(f"❌ Error updating analytics file: {e}")
        import traceback
        traceback.print_exc()

def main():
    """Main function."""
    try:
        print("Starting analytics.py")
        
        # Get Slack client
        client = get_slack_client()
        if not client:
            print("Failed to initialize Slack client")
            return
        
        # Get yesterday's messages
        print("Fetching Slack messages...")
        high_risk_messages = get_yesterday_messages(client, HIGH_RISK_CHANNEL)
        gameday_messages = get_yesterday_messages(client, GAMEDAY_CHANNEL)
        
        # Parse messages
        print("Parsing alert data...")
        high_risk_count = parse_high_risk_alerts(high_risk_messages)
        daily_report = parse_daily_report(gameday_messages)
        
        # Get actual delays from ESPN
        print("Checking ESPN for actual delays...")
        actual_data = get_actual_delays_from_espn()
        
        # Update analytics file
        print("Updating ANALYTICS.md...")
        update_analytics_file(daily_report, high_risk_count, actual_data)
        
        print("✅ Analytics update complete")
    
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
else:
    main()
