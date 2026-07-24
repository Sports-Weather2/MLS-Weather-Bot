"""
weather_bot.py
Updated: July 2026
Weather APIs: National Weather Service (NWS) for USA + OpenWeatherMap for Canada
Main coordinator that:
1. Checks if games are scheduled (ESPN API)
2. If OFF-DAY: Posts once at 7 AM "no games today"
3. If GAME-DAY: Posts daily weather report with all games
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

SLACK_WEBHOOK_GAMEDAY = os.environ.get('SLACK_WEBHOOK_URL')
OPENWEATHERMAP_API_KEY = os.environ.get('OPENWEATHERMAP_API_KEY')

# ─────────────────────────────────────────────────────────────
# IMPACT THRESHOLDS
# ─────────────────────────────────────────────────────────────
IMPACT_RULES = {
    'high_risk': {
        'rain_prob':    80,
        'wind_gust':    30,
        'lightning':    True,
        'temp_extreme': [35, 100]
    },
    'monitor': {
        'rain_prob':      35,
        'wind_sustained': 20,
        'temp_concern':   [40, 95]
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
# IMPACT CALCULATION
# ─────────────────────────────────────────────────────────────
def calculate_game_impact(weather):
    """Calculate weather impact level."""
    rain_prob = weather.get('rain_prob', 0)
    wind_speed = weather.get('wind_speed', 0)
    temp = weather.get('temp', 70)
    has_storm = weather.get('has_thunderstorm', False)
    
    if (rain_prob >= IMPACT_RULES['high_risk']['rain_prob'] or
        wind_speed >= IMPACT_RULES['high_risk']['wind_gust'] or
        has_storm or
        temp <= IMPACT_RULES['high_risk']['temp_extreme'][0] or
        temp >= IMPACT_RULES['high_risk']['temp_extreme'][1]):
        return {
            'level': 'HIGH_RISK',
            'emoji': '🔴',
            'card': '🟥',
            'status': 'HIGH RISK',
            'color': '#dc3545'
        }

    elif (rain_prob >= IMPACT_RULES['monitor']['rain_prob'] or
          wind_speed >= IMPACT_RULES['monitor']['wind_sustained'] or
          temp <= IMPACT_RULES['monitor']['temp_concern'][0] or
          temp >= IMPACT_RULES['monitor']['temp_concern'][1]):
        return {
            'level': 'MONITOR',
            'emoji': '🟡',
            'card': '🟨',
            'status': 'MONITOR',
            'color': '#ffc107'
        }

    else:
        return {
            'level': 'CLEAR',
            'emoji': '🟢',
            'card': '🟩',
            'status': 'CLEAR',
            'color': '#28a745'
        }


def get_delay_probability(weather):
    """Calculate delay probability tier."""
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


# ─────────────────────────────────────────────────────────────
# MESSAGE BUILDERS
# ─────────────────────────────────────────────────────────────
def format_game_block(team_name, game_time, weather, impact):
    """Format a single game weather block (MLS-style with soccer emoji)."""
    weather_details = (
        f"🌡️ *{weather['temp']:.0f}°F*\n"
        f"☁️ {weather['conditions'].title()}\n"
        f"💧 Rain: *{weather['rain_prob']:.0f}%*\n"
        f"💨 Wind: {weather['wind_speed']:.0f} mph"
    )

    impact_details = f"{impact['card']} *{impact['status']}*"
    if impact['level'] == 'HIGH_RISK':
        trigger = build_trigger_reason(weather)
        delay_prob = get_delay_probability(weather)
        impact_details += (
            f"\n📋 *Why:* {trigger}\n"
            f"🎯 *Delay Probability:* {delay_prob}"
        )

    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*⚽ {team_name}*\n{game_time}"
            }
        },
        {
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": f"*Weather Forecast:*\n{weather_details}"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Game Impact:*\n{impact_details}"
                }
            ]
        }
    ]

    if impact['level'] == 'HIGH_RISK':
        blocks.insert(0, {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "⚠️ *WEATHER ALERT* - High risk of game impact"
            }
        })

    return blocks


def build_gameday_weather_message(games_weather):
    """Build daily gameday weather report (7 AM post)."""
    pacific_tz = pytz.timezone('America/Los_Angeles')
    now = datetime.now(pacific_tz)

    high_risk_count = sum(1 for g in games_weather if g['impact']['level'] == 'HIGH_RISK')
    monitor_count = sum(1 for g in games_weather if g['impact']['level'] == 'MONITOR')

    if high_risk_count > 0:
        header_emoji = "⚠️"
        summary = f"{high_risk_count} game(s) at HIGH RISK"
    elif monitor_count > 0:
        header_emoji = "🟡"
        summary = f"{monitor_count} game(s) to MONITOR"
    else:
        header_emoji = "✅"
        summary = "All games clear"

    message = {
        "text": f"⚽ MLS Daily Weather Report: {summary}",
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "⚽ MLS Daily Weather Report",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"{summary} | Next 24 Hours"
                }
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": (
                            f"Updated: {now.strftime('%b %d at %I:%M %p')} PT | "
                            f"Source: 🌐 NWS (USA) + OpenWeatherMap (Canada) | "
                            f"Next update: 7:00 AM PT tomorrow"
                        )
                    }
                ]
            },
            {
                "type": "divider"
            }
        ]
    }

    for game_data in games_weather:
        game_blocks = format_game_block(
            game_data['team_name'],
            game_data['game_time'],
            game_data['weather'],
            game_data['impact']
        )
        message["blocks"].extend(game_blocks)
        message["blocks"].append({"type": "divider"})

    message["blocks"].extend([
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": (
                        "🟩 *CLEAR* - No concerns  |  "
                        "🟨 *MONITOR* - Prepare for possible issues  |  "
                        "🟥 *HIGH RISK* - Significant weather threat"
                    )
                }
            ]
        }
    ])

    return message


def build_offday_message():
    """Build off-day message (when no games scheduled)."""
    pacific_tz = pytz.timezone('America/Los_Angeles')
    now = datetime.now(pacific_tz)
    
    message = {
        "text": "⚽ MLS Daily Weather Report - No Games Scheduled",
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "⚽ MLS Daily Weather Report",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "✅ *No games scheduled today*\n\nMLS Weather Bot is monitoring and will alert on the next game day."
                }
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"Updated: {now.strftime('%b %d at %I:%M %p')} PT"
                    }
                ]
            }
        ]
    }
    
    return message


def post_to_slack(webhook_url, message):
    """Post message to Slack."""
    if not webhook_url:
        print("WARNING: Slack webhook not configured")
        return False
    
    try:
        response = requests.post(
            webhook_url,
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
    """Main weather bot coordinator."""
    print("⚽ Starting MLS Weather Bot...")
    
    pacific_tz = pytz.timezone('America/Los_Angeles')
    now = datetime.now(pacific_tz)
    
    # Check for games today
    print("📅 Checking ESPN API for MLS games today...")
    games = get_mls_games_today()
    
    if not games:
        print("✅ No games scheduled today - posting off-day message once")
        message = build_offday_message()
        post_to_slack(SLACK_WEBHOOK_GAMEDAY, message)
        return
    
    print(f"🎮 Found {len(games)} game(s) today - proceeding with weather check")
    
    # Load stadiums for weather lookup
    stadiums = filter_roofed_stadiums(load_stadiums())
    stadium_map = {s.get('team_name'): s for s in stadiums}
    
    games_weather = []
    
    for event in games:
        try:
            competitors = event.get('competitors', [])
            if len(competitors) < 2:
                continue
            
            home_team = competitors[0].get('team', {}).get('displayName', 'Unknown')
            away_team = competitors[1].get('team', {}).get('displayName', 'Unknown')
            game_time_str = event.get('date', '')
            
            # Try to find stadium by team
            stadium = None
            for comp in competitors:
                team_name = comp.get('team', {}).get('displayName', '')
                if team_name in stadium_map:
                    stadium = stadium_map[team_name]
                    break
            
            if not stadium:
                print(f"⚠️  {away_team} vs {home_team}: Stadium not found in config")
                continue
            
            # Fetch weather
            weather = get_weather_for_stadium(stadium, OPENWEATHERMAP_API_KEY)
            if not weather:
                print(f"⚠️  {away_team} vs {home_team}: No weather data")
                continue
            
            # Calculate impact
            impact = calculate_game_impact(weather)
            
            games_weather.append({
                'team_name': f"{away_team} @ {home_team}",
                'game_time': game_time_str,
                'weather': weather,
                'impact': impact
            })
            
            print(f"✅ {away_team} @ {home_team}: {impact['emoji']} {impact['status']}")
        
        except Exception as e:
            print(f"ERROR processing game: {e}")
            continue
    
    if not games_weather:
        print("⚠️  No games with weather data - posting off-day message")
        message = build_offday_message()
        post_to_slack(SLACK_WEBHOOK_GAMEDAY, message)
        return
    
    # Sort by risk level
    risk_priority = {'HIGH_RISK': 0, 'MONITOR': 1, 'CLEAR': 2}
    games_weather.sort(key=lambda x: risk_priority[x['impact']['level']])
    
    # Post daily weather report
    message = build_gameday_weather_message(games_weather)
    if post_to_slack(SLACK_WEBHOOK_GAMEDAY, message):
        print(f"✅ Daily weather report posted for {len(games_weather)} game(s)")
    else:
        print("❌ Failed to post daily weather report")
    
    print("✅ MLS Weather Bot complete")


if __name__ == "__main__":
    main()
