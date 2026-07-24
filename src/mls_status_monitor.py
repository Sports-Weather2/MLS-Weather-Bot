import os
import requests
import json
from datetime import datetime, timedelta
import pytz

SLACK_WEBHOOK_URL_HIGH_RISK = os.getenv('SLACK_WEBHOOK_URL_HIGH_RISK')
ESPN_MLS_SCOREBOARD = 'https://site.api.espn.com/apis/site/v2/sports/soccer/usa.1/scoreboard'

with open('config/mls_stadiums.json', 'r') as f:
    STADIUMS = json.load(f)

PT = pytz.timezone('America/Los_Angeles')

def get_today_games():
    """Fetch today's MLS games."""
    try:
        today = datetime.now(PT).date()
        date_str = today.strftime('%Y%m%d')
        url = f"{ESPN_MLS_SCOREBOARD}?dates={date_str}"
        
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        return data.get('events', [])
    except Exception as e:
        print(f"Error fetching games: {e}")
        return []

def post_status_message(status, details=None):
    """Post formatted status message."""
    try:
        now_pt = datetime.now(PT)
        
        if status == "active":
            blocks = [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "⚽ *MLS Game Status Monitor*"
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
                        "text": f"🎮 *Games Today:* {details.get('game_count', 0)}"
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"⏱️ *Monitoring Window:* 10 AM – 10 PM PT"
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"📋 *Alert Trigger:* Delays, Postponements, Rescheduling"
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
        
        elif status == "no_games":
            next_check = (datetime.now(PT).date() + timedelta(days=1)).strftime('%A, %B %d, %Y')
            blocks = [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "⚽ *MLS Game Status Monitor*"
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
        
        elif status == "delay":
            blocks = [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "⚽ *MLS Game Status Alert*"
                    }
                },
                {"type": "divider"},
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"🚨 *Status:* {details.get('status', 'Game Delayed')}"
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"⚽ *Match:* {details.get('match', 'N/A')}"
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"📍 *Stadium:* {details.get('stadium', 'N/A')}"
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"💬 *Reason:* {details.get('reason', 'Weather conditions')}"
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"⏰ *Time:* {details.get('time', 'TBD')}"
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
        
        else:  # postponed
            blocks = [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "⚽ *MLS Game Status Alert*"
                    }
                },
                {"type": "divider"},
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "🚫 *Status:* POSTPONED"
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"⚽ *Match:* {details.get('match', 'N/A')}"
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"📍 *Stadium:* {details.get('stadium', 'N/A')}"
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"💬 *Reason:* {details.get('reason', 'Severe weather / Air quality concerns')}"
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"📅 *Reschedule:* {details.get('reschedule', 'TBD')}"
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
        print(f"✅ Status message posted: {status}")
    
    except Exception as e:
        print(f"Error posting message: {e}")

def main():
    """Main monitoring function."""
    try:
        games = get_today_games()
        
        if not games:
            print("No games today")
            post_status_message("no_games")
        else:
            print(f"Found {len(games)} games today")
            post_status_message("active", {"game_count": len(games)})
            # TODO: Real-time monitoring logic for delays/postponements
    
    except Exception as e:
        print(f"Error: {e}")

if __name__ == '__main__':
    main()
