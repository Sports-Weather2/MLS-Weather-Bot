import os
import requests
import json
from datetime import datetime
from src.utils import (
    get_weather_for_stadium,
    get_risk_level,
    get_delay_probability,
    get_aqi_category,
    get_air_quality,
)

SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL_HIGH_RISK")

# Load stadiums
with open('config/mls_stadiums.json', 'r') as f:
    STADIUMS = json.load(f)

def check_all_stadiums_for_high_risk():
    """Check all MLS stadiums for HIGH RISK conditions."""
    high_risk_alerts = []
    
    for stadium in STADIUMS:
        try:
            # Get weather data
            weather_data = get_weather_for_stadium(stadium)
            
            if not weather_data:
                print(f"⚠️ No weather data for {stadium.get('stadium')}")
                continue
            
            # Get air quality
            lat = stadium.get("latitude")
            lon = stadium.get("longitude")
            aqi_data = get_air_quality(lat, lon)
            
            if aqi_data:
                weather_data["aqi"] = aqi_data.get("aqi", 0)
                weather_data["pm25"] = aqi_data.get("pm25", 0)
            
            # Check risk level
            risk_level, why_triggered = get_risk_level(weather_data, stadium)
            
            # Check AQI for HIGH RISK (AQI >= 150)
            aqi = weather_data.get("aqi", 0)
            if aqi >= 150:
                aqi_category = get_aqi_category(aqi)
                aqi_text = f"💨 Air Quality: 🔴 AQI {aqi} ({aqi_category.get('category', 'Unhealthy')})"
                if aqi >= 150 and risk_level != "HIGH RISK":
                    risk_level = "HIGH RISK"
                    why_triggered = aqi_text
                elif aqi >= 150:
                    why_triggered += f" | {aqi_text}"
            
            # Only collect HIGH RISK alerts
            if risk_level == "HIGH RISK":
                delay_prob = get_delay_probability(risk_level, weather_data)
                
                high_risk_alerts.append({
                    "stadium": stadium.get("stadium"),
                    "team": stadium.get("teams", ["Unknown"])[0],
                    "why_triggered": why_triggered,
                    "delay_probability": delay_prob,
                    "weather": weather_data
                })
                
                print(f"🚨 HIGH RISK found: {stadium.get('stadium')} - {why_triggered}")
        
        except Exception as e:
            print(f"❌ Error checking {stadium.get('stadium')}: {e}")
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
                            "text": f"*Team:*\n{alert['team']}"
                        }
                    ]
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Why Triggered:*\n{alert['why_triggered']}"
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Delay Probability:*\n{alert['delay_probability']}"
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
