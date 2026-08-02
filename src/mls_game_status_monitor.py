# mls_game_status_monitor.py
# Real-Time Game Status Monitor for MLS
# Checks every 5 minutes (10 AM - 10 PM PT) for game delays, postponements, and resumptions
# Posts @channel alerts only when game state changes (delays, postponements, resumptions, suspensions)
# DOES NOT post on off-days (off-day alerts handled by weather_bot.py at 7 AM)

import os
import json
import requests
from datetime import datetime
import pytz

SLACK_WEBHOOK = os.environ.get('SLACK_WEBHOOK_URL_HIGH_RISK')
STATE_FILE = 'mls_game_states.json'

# ── Normalized state constants ─────────────────────────────────────────────────
STATE_DELAYED = "DELAYED"
STATE_POSTPONED = "POSTPONED"
STATE_LIVE = "LIVE"
STATE_FINAL = "FINAL"
STATE_PREVIEW = "PREVIEW"
STATE_SUSPENDED = "SUSPENDED"

ESPN_MLS_SCOREBOARD = 'https://site.api.espn.com/apis/site/v2/sports/soccer/usa.1/scoreboard'

with open('config/mls_stadiums.json', 'r') as f:
    STADIUMS = json.load(f)

PT = pytz.timezone('America/Los_Angeles')


def load_game_states():
    """Load previously tracked game states"""
    try:
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def save_game_states(states):
    """Save game states for next run"""
    with open(STATE_FILE, 'w') as f:
        json.dump(states, f, indent=2)


def get_mls_game_status(game_date):
    """Fetch MLS games for today using ESPN API"""
    url = f"{ESPN_MLS_SCOREBOARD}?dates={game_date}"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        games_status = []

        if 'events' in data:
            for event in data['events']:
                try:
                    if 'competitions' not in event:
                        continue

                    comp = event['competitions'][0]
                    competitors = comp.get('competitors', [])

                    if not competitors or len(competitors) < 2:
                        continue

                    home_competitor = next((c for c in competitors if c.get('homeAway') == 'home'), None)
                    away_competitor = next((c for c in competitors if c.get('homeAway') == 'away'), None)

                    if not home_competitor or not away_competitor:
                        continue

                    away_team = away_competitor.get('team', {}).get('displayName', 'Away Team')
                    home_team = home_competitor.get('team', {}).get('displayName', 'Home Team')
                    away_score = away_competitor.get('score', 0)
                    home_score = home_competitor.get('score', 0)

                    # Get game status
                    status = comp.get('status', {})
                    status_type = status.get('type', '')
                    detailed_status = status.get('description', 'Preview')

                    # Get venue info
                    venue_name = comp.get('venue', {}).get('fullName', 'Unknown Stadium')
                    stadium_config = next((s for s in STADIUMS if s['stadium'] == venue_name), None)
                    if not stadium_config:
                        stadium_config = next((s for s in STADIUMS if home_team in s.get('teams', [])), None)

                    roof_type = 'unknown'
                    if stadium_config:
                        roof_type = stadium_config.get('roof', 'open')

                    # Get current time elapsed (minute)
                    current_minute = None
                    if 'summary' in comp:
                        for summary_item in comp['summary']:
                            if summary_item.get('type') == 'time':
                                current_minute = summary_item.get('displayValue', '')

                    # Get game event ID for tracking
                    event_id = event.get('id', '')

                    # Get delay/postponement reason
                    reason = status.get('reason', '')
                    if not reason and 'note' in status:
                        reason = status['note'].get('headline', '')

                    games_status.append({
                        'event_id': event_id,
                        'matchup': f"{away_team} @ {home_team}",
                        'away_team': away_team,
                        'home_team': home_team,
                        'away_score': away_score,
                        'home_score': home_score,
                        'current_minute': current_minute,
                        'status_type': status_type,
                        'detailed_status': detailed_status,
                        'reason': reason,
                        'venue': venue_name,
                        'roof_type': roof_type
                    })

                except Exception as e:
                    print(f"Error processing game: {e}")
                    continue

        return games_status

    except Exception as e:
        print(f"Error fetching MLS game status: {e}")
        return []


def is_weather_related(reason, detailed_status):
    """Check if delay/postponement is weather-related"""
    combined = (detailed_status + ' ' + reason).lower()
    weather_keywords = ['rain', 'weather', 'storm', 'lightning',
                        'inclement', 'wind', 'snow', 'fog', 'thunder']
    return any(keyword in combined for keyword in weather_keywords)


def is_active_weather_delay(game_status):
    """Returns True if game is in active in-game weather delay"""
    detailed = game_status['detailed_status'].lower()

    # Exclude postponed/suspended states
    if 'postponed' in detailed or 'suspend' in detailed:
        return False

    # Check if delayed and weather-related
    is_delayed = 'delay' in detailed or 'delayed' in detailed
    return is_delayed and is_weather_related(game_status['reason'], game_status['detailed_status'])


def is_postponed(game_status):
    """Returns True if game is officially postponed"""
    return 'postponed' in game_status['detailed_status'].lower()


def is_suspended(game_status):
    """Returns True if game is suspended"""
    return 'suspend' in game_status['detailed_status'].lower()


def normalize_api_state(game_status):
    """Convert ESPN API state to normalized internal state constant"""
    detailed = game_status['detailed_status'].lower()
    status_type = game_status['status_type']

    if 'postponed' in detailed:
        return STATE_POSTPONED
    if 'suspend' in detailed:
        return STATE_SUSPENDED
    if 'delay' in detailed:
        return STATE_DELAYED
    if status_type == 'STATUS_IN_PROGRESS':
        return STATE_LIVE
    if status_type == 'STATUS_FINAL':
        return STATE_FINAL
    return STATE_PREVIEW


def get_stadium_type_emoji(roof_type):
    """Return stadium type emoji"""
    if roof_type == 'retractable':
        return '🔄 Retractable Roof'
    elif roof_type == 'domed':
        return '🏟️ Domed'
    else:
        return '☀️ Open Air'


def send_delay_alert(game_status, alert_type):
    """Send @channel alert for delay, resumption, postponement, or suspension"""
    now = datetime.now(PT)

    matchup = game_status['matchup']
    venue = game_status['venue']
    roof_emoji = get_stadium_type_emoji(game_status['roof_type'])

    if alert_type == STATE_DELAYED:
        emoji = "🚨"
        title = "WEATHER DELAY DETECTED"
        text = f"🚨 Weather delay: {matchup}"
    elif alert_type == "RESUME":
        emoji = "✅"
        title = "GAME RESUMING"
        text = f"✅ Game resuming: {matchup}"
    elif alert_type == STATE_POSTPONED:
        emoji = "📅"
        title = "GAME POSTPONED"
        text = f"📅 Game postponed: {matchup}"
    elif alert_type == STATE_SUSPENDED:
        emoji = "⏸️"
        title = "GAME SUSPENDED"
        text = f"⏸️ Game suspended: {matchup}"
    else:
        emoji = "ℹ️"
        title = "GAME STATUS UPDATE"
        text = f"ℹ️ Status update: {matchup}"

    message = {
        "text": text,
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} {title}",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Game:*\n⚽ {matchup}"},
                    {"type": "mrkdwn", "text": f"*Status:*\n{game_status['detailed_status']}"}
                ]
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Venue:*\n{venue}"},
                    {"type": "mrkdwn", "text": f"*Stadium Type:*\n{roof_emoji}"}
                ]
            }
        ]
    }

    # Add score and minute for delay/resume alerts
    if alert_type in [STATE_DELAYED, "RESUME"]:
        away_score = game_status['away_score']
        home_score = game_status['home_score']
        minute = game_status['current_minute'] or 'N/A'

        score_text = f"{game_status['away_team']} {away_score}, {game_status['home_team']} {home_score}"

        message["blocks"].append({
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Score:*\n{score_text}"},
                {"type": "mrkdwn", "text": f"*Current Time:*\n{minute}'"}
            ]
        })

    # Add reason if available
    if game_status['reason']:
        message["blocks"].append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Reason:* {game_status['reason']}"
            }
        })

    # Add retractable roof note
    if game_status['roof_type'] == 'retractable':
        if alert_type in [STATE_DELAYED, STATE_POSTPONED]:
            note = "⚠️ *Note:* Stadium has retractable roof — may have been open or roof malfunction"
            message["blocks"].append({
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": note}]
            })

    # Add timestamp with @channel tag
    message["blocks"].append({
        "type": "context",
        "elements": [
            {
                "type": "mrkdwn",
                "text": f"<!channel> Alert sent at {now.strftime('%I:%M %p')} PT"
            }
        ]
    })

    try:
        response = requests.post(SLACK_WEBHOOK, json=message, timeout=10)

        if response.status_code == 200:
            print(f"✅ {alert_type} alert sent for {matchup}")
        else:
            print(f"❌ Failed to send alert: {response.status_code}")

    except Exception as e:
        print(f"❌ Error sending alert: {e}")


def monitor_games():
    """Monitor games for status changes and send alerts"""
    now = datetime.now(PT)
    today = now.strftime('%Y%m%d')

    print(f"🔍 Monitoring MLS games for {now.strftime('%Y-%m-%d')} ({now.strftime('%I:%M %p PT')})...")

    previous_states = load_game_states()
    current_states = {}

    games = get_mls_game_status(today)

    if not games:
        print("ℹ️  No games found for today (off-day)")
        print("ℹ️  Off-day alert handled by weather_bot.py at 7 AM")
        # Still save empty state for tracking
        save_game_states(current_states)
        return

    print(f"📅 Found {len(games)} game(s)")

    for game in games:
        event_id = game['event_id']
        venue_name = game['venue']
        previous_entry = previous_states.get(event_id, {})
        previous_state = previous_entry.get('state')

        current_normalized = normalize_api_state(game)

        if previous_state is None:
            print(f"   🔍 First seen: {game['matchup']} at {venue_name} — state: {current_normalized}")

        # ── Check order: POSTPONED → SUSPENDED → DELAYED → RESUME ─────────────
        if is_postponed(game) and previous_state != STATE_POSTPONED:
            print(f"📅 POSTPONED: {game['matchup']} at {venue_name}")
            if is_weather_related(game['reason'], game['detailed_status']):
                send_delay_alert(game, STATE_POSTPONED)
            else:
                print(f"   ℹ️  Non-weather postponement — skipping alert")
            current_states[event_id] = {'state': STATE_POSTPONED, 'matchup': game['matchup']}

        elif is_suspended(game) and previous_state != STATE_SUSPENDED:
            print(f"⏸️ SUSPENDED: {game['matchup']} at {venue_name}")
            send_delay_alert(game, STATE_SUSPENDED)
            current_states[event_id] = {'state': STATE_SUSPENDED, 'matchup': game['matchup']}

        elif is_active_weather_delay(game) and previous_state != STATE_DELAYED:
            print(f"🚨 WEATHER DELAY: {game['matchup']} at {venue_name}")
            send_delay_alert(game, STATE_DELAYED)
            current_states[event_id] = {'state': STATE_DELAYED, 'matchup': game['matchup']}

        elif previous_state == STATE_DELAYED and current_normalized == STATE_LIVE:
            print(f"✅ RESUMING: {game['matchup']} at {venue_name}")
            send_delay_alert(game, "RESUME")
            current_states[event_id] = {'state': STATE_LIVE, 'matchup': game['matchup']}

        else:
            current_states[event_id] = {
                'state': previous_state if previous_state else current_normalized,
                'matchup': game['matchup']
            }
            if previous_state:  # Only print if we've seen this game before
                print(f"   ✅ No change: {game['matchup']} — {current_normalized}")

    save_game_states(current_states)
    print(f"\n✅ Monitoring complete — checked {len(games)} games")


def main():
    try:
        monitor_games()
    except Exception as e:
        print(f"❌ Error in game status monitor: {e}")
        raise


if __name__ == "__main__":
    main()
