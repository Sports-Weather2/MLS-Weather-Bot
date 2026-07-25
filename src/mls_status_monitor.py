import os
import requests
import json
from datetime import datetime, timedelta
import pytz

SLACK_WEBHOOK_URL = os.getenv('SLACK_WEBHOOK_URL')
ESPN_MLS_SCOREBOARD = 'https://site.api.espn.com/apis/site/v2/sports/soccer/usa.1/scoreboard'

with open('config/mls_stadiums.json', 'r') as f:
    STADIUMS = json.load(f)

PT = pytz.timezone('America/Los_Angeles')

def get_mls_games_for_date(target_date=None):
    """Fetch MLS games for a specific date."""
    try:
        if target_date is None:
            target_date = datetime.now(PT).date()
        
        date_str = target_date.strftime('%Y%m%d')
        url = f"{ESPN_MLS_SCOREBOARD}?dates={date_str}"
        
        print(f"Fetching games for {date_str}")
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        games = data.get('events', [])
        print(f"Found {len(games)} games on {date_str}")
        return games
    
    except Exception as e:
        print(f"Error fetching games: {e}")
        import traceback
        traceback.print_exc()
        return []

def post_game_status_monitor():
    """Post game status monitor message."""
    try:
        today_games = get_mls_games_for_date()
        game_count = len(today_games)
        
        now_pt = datetime.now(PT)
        current_time = now_pt.strftime('%I:%M %p PT').lstrip('0')
        
        # Determine if games are happening today
        if game_count > 0:
            status_text = "✅ Active & Monitoring"
            games_text = f"{game_count}"
            monitoring_window = "10 AM – 10 PM PT"
            next_check_text = f"Next Check: Today at 6:00 PM PT"
        else:
            status_text = "✅ Active & Monitoring"
            games_text = "0"
            tomorrow = (now_pt + timedelta(days=1)).strftime('%A, %B %d')
            monitoring_window = f"Next game day: {tomorrow}"
            next_check_text = f"Next Check: Tomorrow at 7:00 AM PT"
        
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "⚽ MLS Game Status Monitor",
                    "emoji": True
                }
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"✅ *System Status:* {status_text}\n\n🎮 *Games Scheduled:* {games_text}\n\n⏱️ *Monitoring Window:* {monitoring_window}\n\n📋 *Alert Trigger:* Delays, Postponements, Rescheduling"
                }
            },
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
        response = requests.post(SLACK_WEBHOOK_URL, json=message, timeout=10)
        response.raise_for_status()
        print(f"✅ Game status monitor posted ({game_count} games)")
        
    except Exception as e:
        print(f"❌ Error posting: {e}")
        import traceback
        traceback.print_exc()

def main():
    """Main function."""
    try:
        print("Starting mls_status_monitor.py")
        post_game_status_monitor()
    
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
else:
    main()
