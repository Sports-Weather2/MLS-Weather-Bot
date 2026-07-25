import os
import requests
import json
from datetime import datetime, timezone, timedelta
import pytz

SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")

def get_game_schedule():
    """Fetch today's MLS game schedule from ESPN API (PT timezone)."""
    try:
        # Get today's date in PT
        pt_tz = pytz.timezone('America/Los_Angeles')
        today_pt = datetime.now(pt_tz).date()
        
        response = requests.get(
            "https://site.api.espn.com/apis/site/v2/sports/soccer/usa.1/scoreboard",
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
        
        events = data.get("events", [])
        games_today = []
        
        for event in events:
            # Parse event date and convert to PT
            date_str = event.get("date", "")
            if date_str:
                try:
                    # Parse ISO format date: "2026-07-25T19:30Z"
                    event_dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                    event_date_pt = event_dt.astimezone(pt_tz).date()
                    
                    # Only include games from today (PT)
                    if event_date_pt != today_pt:
                        continue
                except:
                    continue
            
            # Parse competitors array
            competitors = event.get("competitors", [])
            if len(competitors) >= 2:
                home_team = None
                away_team = None
                
                for competitor in competitors:
                    if competitor.get("homeAway") == "home":
                        home_team = competitor.get("team", {}).get("displayName", "Unknown")
                    elif competitor.get("homeAway") == "away":
                        away_team = competitor.get("team", {}).get("displayName", "Unknown")
                
                if home_team and away_team:
                    games_today.append({
                        "home": home_team,
                        "away": away_team,
                        "venue": event.get("venue", {}).get("fullName", "Unknown Venue")
                    })
        
        print(f"✅ Found {len(games_today)} games for today (PT)")
        return games_today
    except Exception as e:
        print(f"Error fetching game schedule: {e}")
        return []


def get_next_game_date():
    """Get the next scheduled game date."""
    try:
        response = requests.get(
            "https://site.api.espn.com/apis/site/v2/sports/soccer/usa.1/scoreboard",
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
        events = data.get("events", [])
        
        if events:
            # Get the first upcoming event's date
            next_event = events[0]
            date_str = next_event.get("date", "")
            if date_str:
                dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                return dt.strftime("%A %B %d")
        
        return "Unknown"
    except Exception as e:
        print(f"Error getting next game date: {e}")
        return "Unknown"


def send_status_monitor(games_count, next_check_date):
    """Send Game Status Monitor to Slack."""
    if not SLACK_WEBHOOK_URL:
        print("Error: SLACK_WEBHOOK_URL not set")
        return False
    
    try:
        if games_count > 0:
            status_text = f"Games Today: {games_count}"
            monitoring_window = "10 AM – 10 PM PT"
        else:
            status_text = "No games today"
            monitoring_window = f"Next Check: {next_check_date}"
        
        payload = {
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "⚽ MLS Game Status Monitor",
                        "emoji": True
                    }
                },
                {
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": f"*Status:*\n✅ Active & Monitoring"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Games Today:*\n{games_count}"
                        }
                    ]
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Monitoring Window:*\n{monitoring_window}"
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Alert Triggers:*\nDelays, Postponements, Rescheduling"
                    }
                },
                {
                    "type": "divider"
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f"Updated: {datetime.now().strftime('%b %d at %I:%M %p %Z')}"
                        }
                    ]
                }
            ]
        }
        
        response = requests.post(SLACK_WEBHOOK_URL, json=payload, timeout=10)
        response.raise_for_status()
        print(f"✅ Game Status Monitor posted: {games_count} games today")
        return True
    
    except Exception as e:
        print(f"❌ Error posting status monitor to Slack: {e}")
        return False


def main():
    """Main execution: post Game Status Monitor."""
    print("🔍 Fetching MLS game schedule...")
    
    games = get_game_schedule()
    games_count = len(games)
    
    next_check_date = get_next_game_date()
    
    print(f"📊 Games today: {games_count}")
    print(f"📅 Next check: {next_check_date}")
    
    send_status_monitor(games_count, next_check_date)


if __name__ == "__main__":
    main()

# Always run main when imported as a module
main()
