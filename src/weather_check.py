"""
Daily weather check for MLS teams.
Runs at 7:00 AM PT via GitHub Actions.
Sends full report to #gameday-weather Slack channel.
"""

import os
import json
import requests
from datetime import datetime
from typing import Dict, List, Tuple
from src.utils import (
    load_stadiums,
    get_stadium_by_team_id,
    filter_roofed_stadiums,
    parse_weather_code,
    convert_time_to_local,
    log_event
)


def get_nws_weather(latitude: float, longitude: float) -> Dict:
    """Fetch weather from NWS API (free, no auth required)."""
    try:
        # Get grid point data first
        points_url = f"https://api.weather.gov/points/{latitude},{longitude}"
        points_response = requests.get(points_url, timeout=10)
        points_response.raise_for_status()
        
        # Extract forecast URL
        forecast_url = points_response.json()['properties']['forecast']
        
        # Get actual forecast
        forecast_response = requests.get(forecast_url, timeout=10)
        forecast_response.raise_for_status()
        
        return forecast_response.json()
    except Exception as e:
        print(f"ERROR fetching NWS weather: {e}")
        return {}


def parse_weather_data(weather_data: Dict) -> Dict:
    """Extract relevant weather metrics from NWS data."""
    try:
        periods = weather_data.get('properties', {}).get('periods', [])
        if not periods:
            return {}
        
        # Get first period (next 12 hours or next day)
        period = periods[0]
        
        return {
            'temperature': period.get('temperature'),
            'temperature_unit': period.get('temperatureUnit'),
            'wind_speed': period.get('windSpeed'),
            'wind_direction': period.get('windDirection'),
            'precipitation_chance': period.get('probabilityOfPrecipitation', {}).get('value'),
            'short_forecast': period.get('shortForecast'),
            'detailed_forecast': period.get('detailedForecast'),
            'time': period.get('startTime'),
        }
    except Exception as e:
        print(f"ERROR parsing weather data: {e}")
        return {}


def assess_weather_condition(weather: Dict) -> Tuple[str, str, str]:
    """
    Assess weather condition tier.
    Returns (tier, emoji, reason).
    
    Tiers:
    - HIGH_RISK: Rain ≥80%, active thunderstorms, temp ≤35°F or ≥100°F, wind ≥30 mph
    - MONITOR: Rain 35-79%, wind ≥20 mph, temp 40-95°F
    - CLEAR: Rain <35%, no severe conditions
    """
    rain_chance = weather.get('precipitation_chance', 0) or 0
    temp = weather.get('temperature', 70)
    wind_speed = weather.get('wind_speed', '0 mph')
    forecast = weather.get('short_forecast', '').lower()
    
    # Parse wind speed (format: "10 mph")
    try:
        wind_mph = int(wind_speed.split()[0])
    except (ValueError, IndexError):
        wind_mph = 0
    
    # Check for thunderstorms (exclude scattered/chance)
    has_storm = ('thunderstorm' in forecast and 
                 'scattered' not in forecast and 
                 'chance' not in forecast)
    
    # HIGH RISK
    if (rain_chance >= 80 or 
        has_storm or 
        temp <= 35 or 
        temp >= 100 or 
        wind_mph >= 30):
        
        reasons = []
        if rain_chance >= 80:
            reasons.append(f"Heavy rain ({rain_chance}%)")
        if has_storm:
            reasons.append("Active thunderstorms")
        if temp <= 35:
            reasons.append(f"Cold temp ({temp}°F)")
        if temp >= 100:
            reasons.append(f"Hot temp ({temp}°F)")
        if wind_mph >= 30:
            reasons.append(f"High wind ({wind_mph} mph)")
        
        return "HIGH_RISK", "🔴", " | ".join(reasons)
    
    # MONITOR
    elif (35 <= rain_chance < 80 or 
          20 <= wind_mph < 30 or 
          40 <= temp < 95):
        
        reasons = []
        if 35 <= rain_chance < 80:
            reasons.append(f"Moderate rain ({rain_chance}%)")
        if 20 <= wind_mph < 30:
            reasons.append(f"Moderate wind ({wind_mph} mph)")
        if 40 <= temp < 50 or 85 <= temp < 95:
            reasons.append(f"Temp {temp}°F")
        
        return "MONITOR", "🟡", " | ".join(reasons)
    
    # CLEAR
    else:
        return "CLEAR", "🟢", "No severe weather"


def build_slack_message(stadiums_weather: List[Dict]) -> str:
    """Build Slack message for #gameday-weather channel."""
    timestamp = datetime.utcnow().isoformat()
    
    message = f"""
🌤️ **MLS Daily Weather Report**
Timestamp: {timestamp} UTC

"""
    
    # Group by tier
    high_risk = [s for s in stadiums_weather if s['tier'] == 'HIGH_RISK']
    monitor = [s for s in stadiums_weather if s['tier'] == 'MONITOR']
    clear = [s for s in stadiums_weather if s['tier'] == 'CLEAR']
    
    if high_risk:
        message += "🔴 **HIGH RISK** (Likely delays)\n"
        for sw in high_risk:
            message += f"• {sw['team_name']} ({sw['city']}) - {sw['reason']}\n"
        message += "\n"
    
    if monitor:
        message += "🟡 **MONITOR** (Watch closely)\n"
        for sw in monitor:
            message += f"• {sw['team_name']} ({sw['city']}) - {sw['reason']}\n"
        message += "\n"
    
    if clear:
        message += f"🟢 **CLEAR** ({len(clear)} stadiums) - No severe weather expected\n"
    
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
        print("✅ Message sent to Slack")
        return True
    except Exception as e:
        print(f"ERROR sending to Slack: {e}")
        return False


def main():
    """Main weather check function."""
    print("🌤️ Starting daily weather check...")
    
    # Load stadiums
    stadiums = filter_roofed_stadiums(load_stadiums())
    if not stadiums:
        print("ERROR: No stadiums loaded")
        return
    
    stadiums_weather = []
    
    for stadium in stadiums:
        team_id = stadium.get('team_id')
        team_name = stadium.get('team_name')
        city = stadium.get('city')
        lat = stadium.get('latitude')
        lon = stadium.get('longitude')
        
        try:
            # Fetch weather
            weather_data = get_nws_weather(lat, lon)
            weather = parse_weather_data(weather_data)
            
            if not weather:
                print(f"⚠️  {team_name}: No weather data")
                continue
            
            # Assess condition
            tier, emoji, reason = assess_weather_condition(weather)
            
            log_event("WEATHER_CHECK", team_id, f"{tier} - {reason}")
            
            stadiums_weather.append({
                'team_id': team_id,
                'team_name': team_name,
                'city': city,
                'weather': weather,
                'tier': tier,
                'emoji': emoji,
                'reason': reason,
            })
            
            print(f"{emoji} {team_name}: {reason}")
        
        except Exception as e:
            print(f"ERROR processing {team_name}: {e}")
    
    # Build and send Slack message
    if stadiums_weather:
        message = build_slack_message(stadiums_weather)
        webhook_url = os.getenv('SLACK_WEBHOOK_URL')
        send_to_slack(webhook_url, message)
    
    print("✅ Weather check complete")


if __name__ == "__main__":
    main()
