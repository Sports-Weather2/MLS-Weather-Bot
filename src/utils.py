import os
import requests
import json
import re
import pytz
from datetime import datetime

OPENWEATHERMAP_API_KEY = os.getenv('OPENWEATHERMAP_API_KEY')
NWS_POINTS_URL = 'https://api.weather.gov/points'
NWS_FORECAST_URL = 'https://api.weather.gov/gridpoints'

# Get the absolute path to config file
script_dir = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(script_dir, '..', 'config', 'mls_stadiums.json')

with open(config_path, 'r') as f:
    STADIUMS = json.load(f)

def get_air_quality(lat, lon):
    """Fetch air quality data from OpenWeatherMap Air Pollution API."""
    try:
        url = f"https://api.openweathermap.org/data/2.5/air_pollution?lat={lat}&lon={lon}&appid={OPENWEATHERMAP_API_KEY}"
        
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # Extract AQI (OpenWeatherMap uses 1-5 scale)
        aqi_value = data.get('list', [{}])[0].get('main', {}).get('aqi', 0)
        
        # Convert OpenWeatherMap scale (1-5) to standard AQI scale (0-500)
        # OpenWeatherMap: 1=Good, 2=Fair, 3=Moderate, 4=Poor, 5=Very Poor
        aqi_conversion = {
            1: 50,    # Good (0-50)
            2: 100,   # Fair (51-100)
            3: 150,   # Moderate (101-150)
            4: 200,   # Poor (151-200)
            5: 300    # Very Poor (201+)
        }
        
        aqi_standard = aqi_conversion.get(aqi_value, 0)
        
        # Get pollutant details
        components = data.get('list', [{}])[0].get('components', {})
        pm25 = round(components.get('pm2_5', 0), 1)
        pm10 = round(components.get('pm10', 0), 1)
        
        print(f"✅ Air Quality fetched: AQI={aqi_standard}, PM2.5={pm25}, PM10={pm10}")
        
        return {
            'aqi': aqi_standard,
            'aqi_level': aqi_value,  # 1-5 scale for reference
            'pm25': pm25,
            'pm10': pm10,
            'source': 'OpenWeatherMap'
        }
    
    except Exception as e:
        print(f"❌ Error fetching air quality: {e}")
        return None

def get_aqi_category(aqi_value):
    """Convert AQI value to category and emoji."""
    if aqi_value <= 50:
        return {'category': 'Good', 'emoji': '🟢', 'level': 'CLEAR'}
    elif aqi_value <= 100:
        return {'category': 'Moderate', 'emoji': '🟡', 'level': 'MONITOR'}
    elif aqi_value <= 150:
        return {'category': 'Unhealthy for Sensitive Groups', 'emoji': '🟠', 'level': 'MONITOR'}
    elif aqi_value <= 200:
        return {'category': 'Unhealthy', 'emoji': '🔴', 'level': 'HIGH RISK'}
    elif aqi_value <= 300:
        return {'category': 'Very Unhealthy', 'emoji': '🟣', 'level': 'HIGH RISK'}
    else:
        return {'category': 'Hazardous', 'emoji': '🔴', 'level': 'CRITICAL'}

def get_weather_for_stadium(stadium_config):
    """
    Fetch weather data for a stadium based on country.
    Routes to NWS (USA) or OpenWeatherMap (Canada).
    """
    try:
        country = stadium_config.get('country', 'USA')
        
        if country == 'USA':
            return get_nws_weather(stadium_config)
        elif country == 'Canada':
            return get_openweathermap_weather(stadium_config)
        else:
            print(f"Unknown country: {country}")
            return None
    
    except Exception as e:
        print(f"Error getting weather: {e}")
        return None

def get_nws_weather(stadium_config):
    """Fetch weather from National Weather Service (USA)."""
    try:
        lat = stadium_config.get('latitude')
        lon = stadium_config.get('longitude')
        
        # Step 1: Get points data to find forecast URL
        points_response = requests.get(f"{NWS_POINTS_URL}/{lat},{lon}", timeout=10)
        points_response.raise_for_status()
        points_data = points_response.json()
        
        forecast_url = points_data.get('properties', {}).get('forecast')
        if not forecast_url:
            print(f"No forecast URL found for {stadium_config.get('stadium')}")
            return None
        
        # Step 2: Get hourly forecast
        forecast_response = requests.get(forecast_url, timeout=10)
        forecast_response.raise_for_status()
        forecast_data = forecast_response.json()
        
        # Get current period (index 0 for next 1-2 hour period)
        periods = forecast_data.get('properties', {}).get('periods', [])
        if not periods:
            print(f"No forecast periods found for {stadium_config.get('stadium')}")
            return None
        
        current = periods[0]
        
        temperature = current.get('temperature', 0)
        condition_short = current.get('shortForecast', 'Unknown')
        
        # Parse detailed weather text for rain/wind/thunderstorms
        detailed_text = current.get('detailedForecast', '').lower()
        
        # Estimate rain probability (NWS doesn't provide explicit %, so we infer)
        rain_prob = 0
        if 'rain' in detailed_text:
            if 'slight' in detailed_text or 'chance' in detailed_text:
                rain_prob = 30
            elif 'likely' in detailed_text:
                rain_prob = 70
            else:
                rain_prob = 50
        
        # Check for thunderstorms
        has_thunderstorms = 'thunderstorm' in detailed_text or 'tstm' in detailed_text
        
        # Extract wind speed (look for pattern like "10 mph" or "10-15 mph")
        wind_speed = 0
        if 'wind' in detailed_text:
            wind_match = re.search(r'(\d+)\s*(?:-\d+)?\s*mph', detailed_text)
            if wind_match:
                wind_speed = int(wind_match.group(1))
        
        return {
            'temperature': temperature,
            'conditions': condition_short,
            'rain_probability': rain_prob,
            'wind_speed': wind_speed,
            'thunderstorms': has_thunderstorms,
            'source': 'NWS'
        }
    
    except Exception as e:
        print(f"Error fetching NWS weather: {e}")
        return None

def get_openweathermap_weather(stadium_config):
    """Fetch weather from OpenWeatherMap (Canada & backup)."""
    try:
        lat = stadium_config.get('latitude')
        lon = stadium_config.get('longitude')
        
        url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={OPENWEATHERMAP_API_KEY}&units=imperial"
        
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        temperature = data.get('main', {}).get('temp', 0)
        condition = data.get('weather', [{}])[0].get('main', 'Unknown')
        wind_speed = data.get('wind', {}).get('speed', 0)
        clouds = data.get('clouds', {}).get('all', 0)
        
        # Estimate rain probability from cloud cover
        rain_prob = clouds // 2  # Simple conversion
        
        # Check for thunderstorms in weather description
        weather_desc = data.get('weather', [{}])[0].get('description', '').lower()
        has_thunderstorms = 'thunderstorm' in weather_desc
        
        # Check for rain in main weather type
        has_rain = data.get('weather', [{}])[0].get('main', '').lower() in ['rain', 'drizzle']
        if has_rain and rain_prob < 50:
            rain_prob = 60
        
        return {
            'temperature': temperature,
            'conditions': condition,
            'rain_probability': rain_prob,
            'wind_speed': wind_speed,
            'thunderstorms': has_thunderstorms,
            'source': 'OpenWeatherMap'
        }
    
    except Exception as e:
        print(f"Error fetching OpenWeatherMap weather: {e}")
        return None

def get_risk_level(weather, stadium_config):
    """
    Determine weather risk level and why it triggered.
    HIGH RISK: Rain ≥80% + thunderstorms, ≥90% rain alone, thunderstorms + wind ≥30mph, 
               temp ≤35°F + wind ≥20mph, wind ≥40mph
    """
    try:
        temp = weather.get('temperature', 0)
        rain = weather.get('rain_probability', 0)
        wind = weather.get('wind_speed', 0)
        storms = weather.get('thunderstorms', False)
        
        why_triggered = ""
        
        # Check for HIGH RISK conditions
        if rain >= 80 and storms:
            why_triggered = f"Heavy rain ({rain}%) + active thunderstorms"
            return 'HIGH RISK', why_triggered
        
        if rain >= 90:
            why_triggered = f"Heavy rain ({rain}%) probability"
            return 'HIGH RISK', why_triggered
        
        if storms and wind >= 30:
            why_triggered = f"Thunderstorms + wind {wind} mph"
            return 'HIGH RISK', why_triggered
        
        if temp <= 35 and wind >= 20:
            why_triggered = f"Extreme cold ({temp}°F) + wind {wind} mph"
            return 'HIGH RISK', why_triggered
        
        if wind >= 40:
            why_triggered = f"Extreme wind {wind} mph"
            return 'HIGH RISK', why_triggered
        
        # Check for MONITOR conditions
        if 35 <= rain <= 79:
            why_triggered = f"Moderate rain chance ({rain}%)"
            return 'MONITOR', why_triggered
        
        if wind >= 20:
            why_triggered = f"Wind {wind} mph"
            return 'MONITOR', why_triggered
        
        if 40 <= temp <= 95:
            why_triggered = f"Temperature {temp}°F"
            return 'MONITOR', why_triggered
        
        if storms:
            why_triggered = "Thunderstorms expected"
            return 'MONITOR', why_triggered
        
        # CLEAR
        return 'CLEAR', "Favorable conditions"
    
    except Exception as e:
        print(f"Error determining risk level: {e}")
        return 'UNKNOWN', f"Error: {e}"

def get_delay_probability(risk_level, weather):
    """
    Calculate estimated delay probability based on weather conditions.
    """
    try:
        rain = weather.get('rain_probability', 0)
        wind = weather.get('wind_speed', 0)
        storms = weather.get('thunderstorms', False)
        temp = weather.get('temperature', 0)
        
        if risk_level == 'HIGH RISK':
            # Very High probability
            if rain >= 90 or (rain >= 80 and storms):
                return '🔴 VERY HIGH — Delay or postponement likely'
            elif storms and rain >= 50:
                return '🟠 HIGH — Delay probable at game time'
            elif wind >= 40:
                return '🔴 VERY HIGH — Extreme wind hazard'
            elif temp <= 35 and wind >= 20:
                return '🟠 HIGH — Extreme cold delay risk'
            else:
                return '🟠 HIGH — Delay probable'
        
        elif risk_level == 'MONITOR':
            if storms or wind >= 30:
                return '🟡 ELEVATED — Monitor closely'
            elif rain >= 60:
                return '🟡 ELEVATED — Possible delays'
            else:
                return '🟡 ELEVATED — Conditions may impact play'
        
        else:
            return '🟢 LOW — Normal operations expected'
    
    except Exception as e:
        print(f"Error calculating delay probability: {e}")
        return 'Unknown'
