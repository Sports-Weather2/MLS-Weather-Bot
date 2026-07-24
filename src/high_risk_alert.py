"""
high_risk_alert.py
Updated: July 2026
Weather APIs: National Weather Service (NWS) for USA + OpenWeatherMap for Canada
10:00 AM PT check for HIGH RISK weather games requiring immediate attention.
Posts ONLY if high-risk conditions exist.
"""

import os
import json
import requests
import pytz
from datetime import datetime, timedelta
from src.utils import (
    load_stadiums,
    filter_roofed_stadiums,
    get_weather_for_stadium,
    log_event
)

SLACK_WEBHOOK = os.environ.get('SLACK_WEBHOOK_URL_HIGH_RISK')
OPENWEATHERMAP_API_KEY = os.environ.get('OPENWEATHERMAP_API_KEY')

# ─────────────────────────────────────────────────────────────
# TIGHTENED THRESHOLDS — NWS + OpenWeatherMap data
# ─────────────────────────────────────────────────────────────
IMPACT_RULES = {
    'high_risk': {
        'rain_prob':    80,
        'wind_gust':    30,
        'lightning':    True,
        'temp_extreme': [35, 100]
    }
}


# ─────────────────────────────────────────────────────────────
# MLS GAMES FETCH
# ─────────────────────────────────────────────────────────────
def get_mls_games_today() -> list:
    """Fetch MLS games for today from ESPN API."""
    try:
        today = datetime.utcnow().strftime("%Y%m%d")
        url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/usa.1/scoreboard?dates={today}"
        
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        events = data.get('events', [])
        
        return events
    except Exception as e:
        print(f"ERROR fetching MLS games: {e}")
        return []


# ─────────────────────────────────────────────────────────────
# RISK CHECK
# ─────────────────────────────────────────────────────────────
def is_high_risk(weather):
    """Check if weather meets HIGH RISK thresholds."""
    rain_prob = weather.get('rain_prob', 0)
    wind_speed = weather.get('wind_speed', 0)
    temp = weather.get('temp', 70)
    has_storm = weather.get('has_thunderstorm', False)
    
    return (
        rain_prob >= IMPACT_RULES['high_risk']['rain_prob'] or
        wind_speed >= IMPACT_RULES['high_risk']['wind_gust'] or
        has_storm or
        temp <= IMPACT_RULES['high_risk']['temp_extreme'][0] or
        temp >= IMPACT_RULES['high_risk']['temp_extreme'][1]
    )


def build_trigger_reason(weather):
    """Build 'why triggered' reason string."""
    trigger_reasons = []
    rain_prob = weather.get('rain_prob', 0)
    temp = weather.get('temp', 70)
    wind_speed = weather.get('wind_speed', 0)
    has_storm = weather.get('has_thunderstorm', False)
    
    if rain_prob >= IMPACT_RULES['high_risk']['rain_prob']:
        trigger_reasons.append(f"Rain {rain_prob:.0f}% ≥ {IMPACT_RULES['high_risk']['rain_prob']}% threshold")
    if has_storm:
        trigger_reasons.append(f"Active thunderstorms + Rain {rain_prob:.0f}%")
    if wind_speed >= IMPACT_RULES['high_risk']['wind_gust']:
        trigger_reasons.append(f"Wind {wind_speed} mph ≥ {IMPACT_RULES['high_risk']['wind_gust']} mph threshold")
    if temp <= IMPACT_RULES['high_risk']['temp_extreme'][0]:
        trigger_reasons.append(f"Temp {temp}°F ≤ {IMPACT_RULES['high_risk']['temp_extreme'][0]}°F threshold")
    if temp >= IMPACT_RULES['high_risk']['temp_extreme'][1]:
        trigger_reasons.append(f"Temp {temp}°F ≥ {IMPACT_RULES['high_risk']['temp_extreme'][1]}°F threshold")
    
    return ' | '.join(trigger_reasons) if trigger_reasons else 'No trigger'


def get_delay_probability(weather):
    """Calculate delay probability language."""
    rain_prob = weather.get('rain_prob', 0)
    temp = weather.get('temp', 70)
    wind_speed = weather.get('wind_speed', 0)
    has_storm = weather.get('has_thunderstorm', False)
    
    # VERY HIGH
    if rain_prob >= 90 or (has_storm and rain_prob >= 70):
        return "🔴 *VERY HIGH* — Delay or postponement likely"
    
    # HIGH
    elif rain_prob >= 80 or (has_storm and rain_prob >= 50):
        return "🟠 *HIGH* — Delay probable at game time"
    
    # ELEVATED
    elif has_storm or wind_speed >= IMPACT_RULES['high_risk']['wind_gust']:
        return "🟡 *ELEVATED* — Conditions may impact play"
    
    elif temp <= IMPACT_RULES['high_risk']['temp_extreme'][0]:
        return "🟡 *ELEVATED* — Extreme cold may impact play"
    
    else:
        return "🟡 *ELEVATED* — Weather warrants monitoring"


# ─────────────────────────────────────────────────────────────
# SLACK MESSAGE BUILDER
# ─────────────────────────────────────────────────────────────
def build_high_risk_message(high_risk_games):
    """Build Slack alert message for high-risk games."""
    pacific_tz = pytz.timezone('America/Los_Angeles')
    now = datetime.now(pacific_tz)

    if not high_risk_games:
        return {
            "text": "✅ No high-risk weather games",
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "✅ All Clear - No High-Risk Weather Games",
                        "emoji": True
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "No MLS games currently at high risk due to weather."
                    }
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": (
                                f"Checked at {now.strftime('%I:%M %p')} PT  |  "
                                f"Source: 🌐 NWS (USA) + OpenWeatherMap (Canada)"
                            )
                        }
                    ]
                }
            ]
        }

    message = {
        "text": f"🚨 {len(high_risk_games)} HIGH RISK weather game(s)",
        "blocks": [
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
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*{len(high_risk_games)} game(s) at HIGH RISK* requiring attention "
                        f"for daypart/guide adjustments"
                    )
                }
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": (
                            f"Updated: {now.strftime('%I:%M %p')} PT  |  "
                            f"Source: 🌐 NWS (USA) + OpenWeatherMap (Canada)"
                        )
                    }
                ]
            },
            {
                "type": "divider"
            }
        ]
    }

    for game_data in high_risk_games:
        weather = game_data['weather']
        team_name = game_data['team_name']
        game_time = game_data['game_time']

        weather_details = f"🌡️ {weather['temp']:.0f}°F  |  "
        weather_details += f"💧 Rain: *{weather['rain_prob']:.0f}%*  |  "
        weather_details += f"💨 Wind: {weather['wind_speed']:.0f} mph"

        if weather['wind_speed'] > weather['wind_speed'] + 5:
            weather_details += f" (gusts {weather['wind_speed']:.0f} mph)"

        if weather['has_thunderstorm']:
            weather_details += "  |  ⚡ *Thunderstorms*"

        trigger = build_trigger_reason(weather)
        delay_prob = get_delay_probability(weather)

        message["blocks"].append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*🔴 ⚽ {team_name}*\n"
                    f"{game_time}\n"
                    f"{weather_details}\n"
                    f"📋 *Why:* {trigger}\n"
                    f"🎯 *Delay Probability:* {delay_prob}"
                )
            }
        })
        message["blocks"].append({"type": "divider"})

    message["blocks"].append({
        "type": "context",
        "elements": [
            {
                "type": "mrkdwn",
                "text": (
                    "🟥 *HIGH RISK* = ≥80% rain OR thunderstorms (≥40% rain) OR "
                    "temps ≤35°F / ≥100°F OR wind ≥30 mph"
                )
            }
        ]
    })

    return message


def post_to_slack(message):
    """Post message to Slack webhook."""
    if not SLACK_WEBHOOK:
        print("WARNING: SLACK_WEBHOOK_URL_HIGH_RISK not configured")
        return False
    
    try:
        response = requests.post(
            SLACK_WEBHOOK,
            json=message,
            headers={'Content-Type': 'application/json'},
            timeout=10
        )
        if response.status_code != 200:
            print(f"ERROR: Slack request failed: {response.status_code}")
            return False
        return True
    except Exception as e:
        print(f"ERROR posting to Slack: {e}")
        return False


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────
def main():
    """Main high-risk alert function."""
    print("🚨 Starting MLS high-risk weather alert check...")
    
    pacific_tz = pytz.timezone('America/Los_Angeles')
    now = datetime.now(pacific_tz)

    # Check for games today
    print("📅 Checking ESPN API for MLS games today...")
    games = get_mls_games_today()
    
    if not games:
        print("✅ No games scheduled today - skipping alert")
        return

    print(f"🎮 Found {len(games)} game(s) - checking for high-risk weather...\n")

    # Load stadiums for weather lookup
    stadiums = filter_roofed_stadiums(load_stadiums())
    stadium_map = {s.get('team_name'): s for s in stadiums}

    high_risk_games = []
    
    for event in games:
        try:
            competitors = event.get('competitors', [])
            if len(competitors) < 2:
                continue
            
            home_team = competitors[0].get('team', {}).get('displayName', 'Unknown')
            away_team = competitors[1].get('team', {}).get('displayName', 'Unknown')
            game_time_str = event.get('date', '')
            team_name = f"{away_team} @ {home_team}"
            
            # Try to find stadium by team
            stadium = None
            for comp in competitors:
                team_name_lookup = comp.get('team', {}).get('displayName', '')
                if team_name_lookup in stadium_map:
                    stadium = stadium_map[team_name_lookup]
                    break
            
            if not stadium:
                print(f"⚠️  {team_name}: Stadium not found in config")
                continue
            
            # Fetch weather
            weather = get_weather_for_stadium(stadium, OPENWEATHERMAP_API_KEY)
            if not weather:
                print(f"⚠️  {team_name}: No weather data")
                continue
            
            # Check if high risk
            if is_high_risk(weather):
                log_event("HIGH_RISK_ALERT", stadium.get('team_id', ''), build_trigger_reason(weather))
                high_risk_games.append({
                    'team_name': team_name,
                    'game_time': game_time_str,
                    'weather': weather
                })
                print(f"🔴 HIGH RISK: {team_name}")
            else:
                print(f"✅ CLEAR: {team_name}")
        
        except Exception as e:
            print(f"ERROR processing game: {e}")
            continue

    print(f"\n📊 Found {len(high_risk_games)} high-risk game(s)\n")

    # Build and post message
    message = build_high_risk_message(high_risk_games)

    if post_to_slack(message):
        if high_risk_games:
            print(f"✅ High-risk alert posted for {len(high_risk_games)} game(s)")
        else:
            print("✅ All-clear message posted")
    else:
        print("❌ Failed to post to Slack")

    print("✅ High-risk alert check complete")


if __name__ == "__main__":
    main()
