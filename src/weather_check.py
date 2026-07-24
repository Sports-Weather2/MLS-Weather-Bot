"""
Daily weather check for MLS teams.
Runs at 7:00 AM PT via GitHub Actions.
Fetches weather for all games and posts to #mls-gameday-weather Slack channel.
Uses NWS API for USA stadiums and OpenWeatherMap for Canada stadiums.
"""

import os
import json
import requests
from datetime import datetime
from typing import Dict, List, Tuple
from src.utils import (
    load_stadiums,
    filter_roofed_stadiums,
    parse_weather_code,
    log_event,
    get_weather_for_stadium
)


def assess_weather_condition(weather: Dict) -> Tuple[str, str, str]:
    """
    Assess weather condition and return tier.
    
    Returns (tier, emoji, description).
    
    Tiers:
    - HIGH_RISK: Rain ≥80%, active thunderstorms, temp ≤35°F or ≥100°F, wind ≥30 mph
    - MONITOR: Rain 35-79%, wind 20-29 mph, temp 40-95°F
    - CLEAR: Rain <35%, no severe conditions
    """
    rain_chance = weather.get('precipitation_chance', 0) or 0
    temp = weather.get('temperature', 70)
    wind_speed = weather.get('wind_speed', '0 mph')
    forecast = weather.get('short_forecast', '').lower()
    
    # Parse wind speed
    try:
        wind_mph = int(wind_speed.split()[0])
    except (ValueError, IndexError):
        wind_mph = 0
    
    # Check for thunderstorms (exclude scattered/chance)
    has_storm = ('thunderstorm' in forecast and 
                 'scattered' not in forecast and 
                 'chance' not in forecast)
    
    # HIGH RISK conditions
    if rain_chance >= 80 or has_storm or temp <= 35 or temp >= 100 or wind_mph >= 30:
        return "HIGH_RISK", "🔴", f"Rain {rain_chance}%, Temp {temp}°F, Wind {wind_mph} mph"
    
    # MONITOR conditions
    elif (35 <= rain_chance < 80) or (20 <= wind_mph < 30) or (40 <= temp < 95):
        return "MONITOR", "🟡", f"Rain {rain_chance}%, Temp {temp}°F, Wind {wind_mph} mph"
    
    # CLEAR
    else:
        return "CLEAR", "🟢", f"Rain {rain_chance}%, Temp {temp}°F"


def build_weather_report_message(stadiums_by_tier: Dict[str, List[Dict]], total_stadiums: int) -> str:
    """Build Slack message for daily weather report."""
    timestamp = datetime.utcnow().isoformat()
    
    message = f"""**🌤️ MLS Daily Weather Report**
Timestamp: {timestamp} UTC
Total Stadiums: {total_stadiums}
Source: 🌐 National Weather Service (USA) + OpenWeatherMap (Canada)

"""
    
    # HIGH RISK section
    if stadiums_by_tier.get('HIGH_RISK'):
        message += "🔴 **HIGH RISK** (Likely delays)\n"
        for s in stadiums_by_tier['HIGH_RISK']:
            message += f"• {s['team_name']} ({s['city']}) - {s['description']}\n"
            message += f"  Temp: {s['weather']['temperature']}°F | Wind: {s['weather']['wind_speed']} | Rain: {s['weather']['precipitation_chance']}%\n"
        message += "\n"
    
    # MONITOR section
    if stadiums_by_tier.get('MONITOR'):
        message += "🟡 **MONITOR** (Watch closely)\n"
        for s in stadiums_by_tier['MONITOR']:
            message += f"• {s['team_name']} ({s['city']}) - {s['description']}\n"
            message += f"  Temp: {s['weather']['temperature']}°F | Wind: {s['weather']['wind_speed']} | Rain: {s['weather']['precipitation_chance']}%\n"
        message += "\n"
    
    # CLEAR section
    if stadiums_by_tier.get('CLEAR'):
        message += f"🟢 **CLEAR** ({len(stadiums_by_tier['CLEAR'])} stadiums) - No severe weather expected\n"
    
    message += "\n_Use roofed stadiums (ATL, HOU, VAN) as backup if conditions worsen._"
    
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
        print("✅ Weather report sent to Slack")
        return True
    except Exception as e:
        print(f"ERROR sending to Slack: {e}")
        return False


def main():
    """Main weather check function."""
    print("🌤️ Starting MLS Daily Weather Check...")
    
    # Load stadiums
    stadiums = filter_roofed_stadiums(load_stadiums())
    if not stadiums:
        print("ERROR: No stadiums loaded")
        return
    
    print(f"📍 Checking weather for {len(stadiums)} open-air stadiums")
    
    # Get OpenWeatherMap API key for Canada stadiums
    openweathermap_api_key = os.getenv('OPENWEATHERMAP_API_KEY')
    if not openweathermap_api_key:
        print("WARNING: OPENWEATHERMAP_API_KEY not configured (Canada stadiums will fail)")
    
    # Organize stadiums by weather tier
    stadiums_by_tier = {
        'HIGH_RISK': [],
        'MONITOR': [],
        'CLEAR': []
    }
    
    # Fetch weather for each stadium
    for stadium in stadiums:
        team_id = stadium.get('team_id')
        team_name = stadium.get('team_name')
        city = stadium.get('city')
        country = stadium.get('country', 'USA')
        
        try:
            # Fetch weather using appropriate API
            weather = get_weather_for_stadium(stadium, openweathermap_api_key)
            
            if not weather:
                print(f"⚠️  {team_name}: No weather data")
                continue
            
            # Assess condition
            tier, emoji, description = assess_weather_condition(weather)
            
            stadium_report = {
                'team_id': team_id,
                'team_name': team_name,
                'city': city,
                'country': country,
                'weather': weather,
                'tier': tier,
                'emoji': emoji,
                'description': description,
            }
            
            stadiums_by_tier[tier].append(stadium_report)
            
            log_event("WEATHER_CHECK", team_id, f"{tier} - {description}")
            print(f"{emoji} {team_name} ({country}): {tier} - {description}")
        
        except Exception as e:
            print(f"ERROR processing {team_name}: {e}")
    
    # Build and send Slack message
    webhook_url = os.getenv('SLACK_WEBHOOK_URL')
    message = build_weather_report_message(stadiums_by_tier, len(stadiums))
    send_to_slack(webhook_url, message)
    
    print("✅ Daily weather check complete")


if __name__ == "__main__":
    main()
