"""
High-risk weather alert monitor for MLS teams.
Runs at 10:00 AM PT via GitHub Actions.
Monitors every 10 minutes from 10 AM–10 PM PT for severe conditions.
Sends alerts to #mls-high-risk-weather Slack channel.
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
        
        # Get first period
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


def calculate_delay_probability(weather: Dict) -> Tuple[str, str]:
    """
    Calculate game delay probability tier.
    Returns (tier, emoji).
    
    Tiers:
    - VERY_HIGH: Rain ≥90% or (storms + rain ≥70%)
    - HIGH: Rain ≥80% or (storms + rain ≥50%)
    - ELEVATED: Active storms OR wind ≥30 mph OR temp ≤35°F
    - MODERATE: Rain 35-79% OR wind 20-29 mph
    - LOW: Rain <35%, no severe conditions
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
    
    # VERY HIGH
    if rain_chance >= 90 or (has_storm and rain_chance >= 70):
        return "VERY_HIGH", "🔴"
    
    # HIGH
    elif rain_chance >= 80 or (has_storm and rain_chance >= 50):
        return "HIGH", "🟠"
    
    # ELEVATED
    elif has_storm or wind_mph >= 30 or temp <= 35:
        return "ELEVATED", "🟡"
    
    # MODERATE
    elif 35 <= rain_chance < 80 or 20 <= wind_mph < 30:
        return "MODERATE", "🔵"
    
    # LOW
    else:
        return "LOW", "🟢"


def assess_high_risk_alert(weather: Dict) -> Tuple[bool, str, str, str]:
    """
    Determine if alert should be triggered.
    Returns (should_alert, tier, emoji, reason).
    
    Alert triggers (IMMEDIATE):
    - Rain ≥80% + active thunderstorms
    - Rain ≥90%
    - Active thunderstorms + wind ≥30 mph
    - Temp ≤35°F + wind ≥20 mph
    - Wind ≥40 mph
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
    
    # Check for thunderstorms
    has_storm = ('thunderstorm' in forecast and 
                 'scattered' not in forecast and 
                 'chance' not in forecast)
    
    # Condition 1: Heavy rain + thunderstorms
    if rain_chance >= 80 and has_storm:
        delay_tier, emoji = calculate_delay_probability(weather)
        return True, delay_tier, emoji, f"Heavy rain ({rain_chance}%) + thunderstorms"
    
    # Condition 2: Extreme rain
    if rain_chance >= 90:
        delay_tier, emoji = calculate_delay_probability(weather)
        return True, delay_tier, emoji, f"Extreme rain ({rain_chance}%)"
    
    # Condition 3: Thunderstorms + high wind
    if has_storm and wind_mph >= 30:
        delay_tier, emoji = calculate_delay_probability(weather)
        return True, delay_tier, emoji, f"Thunderstorms + wind {wind_mph} mph"
    
    # Condition 4: Cold + moderate wind
    if temp <= 35 and wind_mph >= 20:
        delay_tier, emoji = calculate_delay_probability(weather)
        return True, delay_tier, emoji, f"Cold ({temp}°F) + wind {wind_mph} mph"
    
    # Condition 5: Extreme wind
    if wind_mph >= 40:
        delay_tier, emoji = calculate_delay_probability(weather)
        return True, delay_tier, emoji, f"Extreme wind {wind_mph} mph"
    
    # No alert
    delay_tier, emoji = calculate_delay_probability(weather)
    return False, delay_tier, emoji, "Monitoring"


def build_high_risk_message(alert_stadiums: List[Dict]) -> str:
    """Build Slack alert message for #mls-high-risk-weather."""
    timestamp = datetime.utcnow().isoformat()
    
    message = f"""
🚨 **MLS High-Risk Weather Alert**
Timestamp: {timestamp} UTC
Total Alerts: {len(alert_stadiums)}

"""
    
    # Group by delay tier
    very_high = [s for s in alert_stadiums if s['delay_tier'] == 'VERY_HIGH']
    high = [s for s in alert_stadiums if s['delay_tier'] == 'HIGH']
    elevated = [s for s in alert_stadiums if s['delay_tier'] == 'ELEVATED']
    
    if very_high:
        message += "🔴 **VERY HIGH DELAY RISK**\n"
        for s in very_high:
            message += f"• {s['team_name']} ({s['city']}) - {s['reason']}\n"
            message += f"  Temp: {s['weather']['temperature']}°F | Wind: {s['weather']['wind_speed']} | Rain: {s['weather']['precipitation_chance']}%\n"
        message += "\n"
    
    if high:
        message += "🟠 **HIGH DELAY RISK**\n"
        for s in high:
            message += f"• {s['team_name']} ({s['city']}) - {s['reason']}\n"
            message += f"  Temp: {s['weather']['temperature']}°F | Wind: {s['weather']['wind_speed']} | Rain: {s['weather']['precipitation_chance']}%\n"
        message += "\n"
    
    if elevated:
        message += "🟡 **ELEVATED DELAY RISK** (Monitor closely)\n"
        for s in elevated:
            message += f"• {s['team_name']} ({s['city']}) - {s['reason']}\n"
        message += "\n"
    
    message += "_Next check in 10 minutes. Roofed stadiums: ATL, HOU, VAN_"
    
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
        print("✅ Alert sent to Slack")
        return True
    except Exception as e:
        print(f"ERROR sending to Slack: {e}")
        return False


def main():
    """Main high-risk alert function."""
    print("🚨 Starting high-risk weather alert check...")
    
    # Load stadiums
    stadiums = filter_roofed_stadiums(load_stadiums())
    if not stadiums:
        print("ERROR: No stadiums loaded")
        return
    
    alert_stadiums = []
    
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
            
            # Assess alert condition
            should_alert, delay_tier, emoji, reason = assess_high_risk_alert(weather)
            
            if should_alert:
                log_event("HIGH_RISK_ALERT", team_id, reason)
                alert_stadiums.append({
                    'team_id': team_id,
                    'team_name': team_name,
                    'city': city,
                    'weather': weather,
                    'delay_tier': delay_tier,
                    'emoji': emoji,
                    'reason': reason,
                })
                print(f"{emoji} ALERT: {team_name} - {reason}")
            else:
                print(f"✅ {team_name}: {reason}")
        
        except Exception as e:
            print(f"ERROR processing {team_name}: {e}")
    
    # Build and send Slack message if there are alerts
    if alert_stadiums:
        message = build_high_risk_message(alert_stadiums)
        webhook_url = os.getenv('SLACK_WEBHOOK_URL')
        send_to_slack(webhook_url, message)
    else:
        print("✅ No high-risk alerts triggered")
    
    print("✅ High-risk alert check complete")


if __name__ == "__main__":
    main()
