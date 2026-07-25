import os
import requests
import json
from datetime import datetime
from src.utils import (
    get_nws_forecast,
    get_openweathermap_forecast,
    get_air_quality,
    get_aqi_category,
    get_stadium_coordinates,
    get_all_stadiums,
)

SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL_HIGH_RISK")

def check_high_risk_conditions(weather_data):
    """
    Check if weather conditions meet HIGH RISK threshold.
    Returns (is_high_risk, reason)
    """
    if not weather_data:
        return False, ""
    
    rain_prob = weather_data.get("rain_prob", 0)
    wind_speed = weather_data.get("wind_speed", 0)
    temp = weather_data.get("temp", 50)
    has_thunderstorm = weather_data.get("thunderstorm", False)
    aqi = weather_data.get("aqi", 0)
    
    reasons = []
    
    # HIGH RISK: Rain ≥80% + thunderstorms
    if rain_prob >= 80 and has_thunderstorm:
        reasons.append(f"🌧️ Heavy Rain ({rain_prob}%) + Thunderstorms")
    
    # HIGH RISK: Rain ≥90% standalone
    if rain_prob >= 90:
        reasons.append(f"🌧️ Extreme Rain ({rain_prob}%)")
    
    # HIGH RISK: Thunderstorms + wind ≥30 mph
    if has_thunderstorm and wind_speed >= 30:
        reasons.append(f"⚡ Thunderstorms + Strong Wind ({wind_speed} mph)")
    
    # HIGH RISK: Temp ≤35°F + wind ≥20 mph
    if temp <= 35 and wind_speed >= 20:
        reasons.append(f"🥶 Cold ({temp}°F) + Wind ({wind_speed} mph)")
    
    # HIGH RISK: Wind ≥40 mph
    if wind_speed >= 40:
        reasons.append(f"💨 Extreme Wind ({wind_speed} mph)")
    
    # HIGH RISK: AQI ≥150 (Unhealthy)
    if aqi >= 150:
        aqi_category = get_aqi_category(aqi)
        reasons.append(f"💨 Air Quality: 🔴 AQI {aqi} ({aqi_category})")
    
    is_high_risk = len(reasons) > 0
    return is_high_risk, " | ".join(reasons)


def get_game_schedule():
    """Fetch today's MLS game schedule from ESPN API."""
    try:
        response = requests.get(
            "https://site.api.espn.com/apis/site/v2/sports/soccer/usa.1/scoreboard",
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
        
        events = data.get("events", [])
        games_today = []
        
        for event in events:
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
        
        return games_today
    except Exception as e:
        print(f"Error fetching game schedule: {e}")
        return []


def check_all_stadiums_for_high_risk():
    """Check all MLS stadiums for HIGH RISK conditions."""
    stadiums = get_all_stadiums()
    high_risk_alerts = []
    
    for stadium in stadiums:
        stadium_name = stadium.get("name")
        lat = stadium.get("lat")
        lon = stadium.get("lon")
        api_source = stadium.get("api_source", "nws")
        
        try:
            # Get weather data
            if api_source == "openweathermap":
                weather_data = get_openweathermap_forecast(lat, lon)
            else:  # nws
                weather_data = get_nws_forecast(lat, lon)
            
            # Get air quality
            aqi = get_air_quality(lat, lon)
            if weather_data:
                weather_data["aqi"] = aqi
            
            # Check for high risk
            is_high_risk, reason = check_high_risk_conditions(weather_data)
            
            if is_high_risk:
                high_risk_alerts.append({
                    "stadium": stadium_name,
                    "reason": reason,
                    "lat": lat,
                    "lon": lon
                })
        
        except Exception as e:
            print(f"Error checking {stadium_name}: {e}")
            continue
    
    return high_risk_alerts


def send_slack_alert(alert):
    """Send HIGH RISK alert to Slack."""
    if not SLACK_WEBHOOK_URL:
        print("Error: SLACK_WEBHOOK_URL_HIGH_RISK not set")
        return False
    
    try:
        payload = {
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "⚠️ MLS HIGH RISK Weather Alert",
                        "emoji": True
                    }
                },
                {
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": f"*Stadium:*\n{alert['stadium']}"
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Why Triggered:*\n{alert['reason']}"
                        }
                    ]
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
        print(f"✅ HIGH RISK alert posted for {alert['stadium']}")
        return True
    
    except Exception as e:
        print(f"❌ Error posting alert to Slack: {e}")
        return False


def main():
    """Main execution: check all stadiums and post HIGH RISK alerts only."""
    print("🔍 Checking MLS stadiums for HIGH RISK conditions...")
    
    high_risk_alerts = check_all_stadiums_for_high_risk()
    
    if high_risk_alerts:
        print(f"🚨 Found {len(high_risk_alerts)} stadium(s) with HIGH RISK conditions!")
        for alert in high_risk_alerts:
            send_slack_alert(alert)
    else:
        print("✅ No HIGH RISK conditions detected. No alerts posted.")


if __name__ == "__main__":
    main()
