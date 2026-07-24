"""
Utility functions for MLS Weather Bot.
"""

import json
import requests
import pytz
from datetime import datetime
from typing import Dict, List, Optional, Tuple


def load_stadiums() -> List[Dict]:
    """Load MLS stadium configuration from JSON file."""
    try:
        with open('config/mls_stadiums.json', 'r') as f:
            data = json.load(f)
            return data.get('teams', [])
    except FileNotFoundError:
        print("ERROR: config/mls_stadiums.json not found")
        return []
    except json.JSONDecodeError:
        print("ERROR: Invalid JSON in config/mls_stadiums.json")
        return []


def get_stadium_by_team_id(team_id: str, stadiums: List[Dict]) -> Optional[Dict]:
    """Get stadium info by team ID."""
    for stadium in stadiums:
        if stadium.get('team_id') == team_id:
            return stadium
    return None


def get_local_time(latitude: float, longitude: float) -> datetime:
    """Get current local time at given coordinates using timezone."""
    # Determine timezone from stadiums list
    stadiums = load_stadiums()
    for stadium in stadiums:
        if (abs(stadium['latitude'] - latitude) < 0.01 and 
            abs(stadium['longitude'] - longitude) < 0.01):
            tz = pytz.timezone(stadium['timezone'])
            return datetime.now(tz)
    
    # Fallback to UTC if not found
    return datetime.now(pytz.UTC)


def format_alert_message(team_name: str, stadium: str, city: str, 
                        condition: str, reason: str) -> str:
    """Format alert message for Slack."""
    return f"""
🚨 **{team_name}** ({city})
Stadium: {stadium}
Condition: {condition}
Reason: {reason}
"""


def is_game_day(team_id: str) -> bool:
    """Check if there's a game scheduled for the team today."""
    # Placeholder for ESPN/MLS API integration
    return True


def filter_roofed_stadiums(stadiums: List[Dict]) -> List[Dict]:
    """Return only open-air stadiums (exclude roofed ones)."""
    return [s for s in stadiums if not s.get('roofed', False)]


def get_timezone_for_stadium(stadium: Dict) -> pytz.timezone:
    """Get pytz timezone object for a stadium."""
    return pytz.timezone(stadium.get('timezone', 'US/Eastern'))


def convert_time_to_local(dt: datetime, timezone_str: str) -> datetime:
    """Convert datetime to local timezone."""
    tz = pytz.timezone(timezone_str)
    if dt.tzinfo is None:
        dt = pytz.UTC.localize(dt)
    return dt.astimezone(tz)


def parse_weather_code(code: int) -> Tuple[str, str]:
    """
    Parse WMO weather code to description and emoji.
    Returns (description, emoji).
    """
    weather_codes = {
        0: ("Clear sky", "☀️"),
        1: ("Mainly clear", "🌤️"),
        2: ("Partly cloudy", "⛅"),
        3: ("Overcast", "☁️"),
        45: ("Foggy", "🌫️"),
        48: ("Foggy (rime)", "🌫️"),
        51: ("Light drizzle", "🌧️"),
        53: ("Moderate drizzle", "🌧️"),
        55: ("Dense drizzle", "🌧️"),
        61: ("Slight rain", "🌧️"),
        63: ("Moderate rain", "🌧️"),
        65: ("Heavy rain", "⛈️"),
        71: ("Slight snow", "❄️"),
        73: ("Moderate snow", "❄️"),
        75: ("Heavy snow", "❄️"),
        77: ("Snow grains", "❄️"),
        80: ("Slight rain showers", "🌧️"),
        81: ("Moderate rain showers", "🌧️"),
        82: ("Violent rain showers", "⛈️"),
        85: ("Slight snow showers", "❄️"),
        86: ("Heavy snow showers", "❄️"),
        95: ("Thunderstorm", "⛈️"),
        96: ("Thunderstorm with hail", "⛈️"),
        99: ("Thunderstorm with hail", "⛈️"),
    }
    desc, emoji = weather_codes.get(code, ("Unknown", "❓"))
    return desc, emoji


def log_event(event_type: str, team_id: str, message: str):
    """Log event for debugging and audit trail."""
    timestamp = datetime.now().isoformat()
    log_entry = f"[{timestamp}] {event_type} - {team_id}: {message}"
    print(log_entry)
    # In production, could write to file or cloud logging service


def get_weather_api_for_stadium(stadium: Dict) -> str:
    """
    Determine which weather API to use based on stadium location.
    
    Returns:
    - "NWS" for USA stadiums
    - "OPENWEATHERMAP" for Canada stadiums
    """
    country = stadium.get('country', 'USA')
    
    if country.upper() == 'CANADA':
        return "OPENWEATHERMAP"
    else:
        return "NWS"


def get_nws_weather(latitude: float, longitude: float) -> Dict:
    """
    Fetch weather from NWS API (free, no auth required).
    Used for USA stadiums.
    """
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


def get_openweathermap_weather(latitude: float, longitude: float, api_key: str) -> Dict:
    """
    Fetch weather from OpenWeatherMap API.
    Used for Canada stadiums.
    
    Args:
        latitude: Stadium latitude
        longitude: Stadium longitude
        api_key: OpenWeatherMap API key
    """
    try:
        url = f"https://api.openweathermap.org/data/2.5/forecast?lat={latitude}&lon={longitude}&appid={api_key}&units=metric"
        
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        return response.json()
    except Exception as e:
        print(f"ERROR fetching OpenWeatherMap weather: {e}")
        return {}


def parse_nws_weather_data(weather_data: Dict) -> Dict:
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
        print(f"ERROR parsing NWS weather data: {e}")
        return {}


def parse_openweathermap_weather_data(weather_data: Dict) -> Dict:
    """Extract relevant weather metrics from OpenWeatherMap data."""
    try:
        # Get first forecast period (3 hours from now)
        list_data = weather_data.get('list', [])
        if not list_data:
            return {}
        
        period = list_data[0]
        
        # Extract temperature (convert from Celsius to Fahrenheit for consistency)
        temp_c = period.get('main', {}).get('temp', 0)
        temp_f = (temp_c * 9/5) + 32
        
        # Extract wind speed (convert from m/s to mph)
        wind_mps = period.get('wind', {}).get('speed', 0)
        wind_mph = wind_mps * 2.237
        
        # Extract precipitation probability (OpenWeatherMap gives as decimal 0-1)
        pop = period.get('pop', 0)
        precipitation_chance = int(pop * 100)
        
        # Extract forecast description
        description = ''
        weather_list = period.get('weather', [])
        if weather_list:
            description = weather_list[0].get('main', '') + ' - ' + weather_list[0].get('description', '')
        
        return {
            'temperature': int(temp_f),
            'temperature_unit': 'F',
            'wind_speed': f"{int(wind_mph)} mph",
            'wind_direction': '',
            'precipitation_chance': precipitation_chance,
            'short_forecast': description,
            'detailed_forecast': description,
            'time': period.get('dt_txt'),
        }
    except Exception as e:
        print(f"ERROR parsing OpenWeatherMap weather data: {e}")
        return {}


def get_weather_for_stadium(stadium: Dict, api_key: Optional[str] = None) -> Dict:
    """
    Get weather for a stadium using appropriate API.
    
    Args:
        stadium: Stadium dictionary with location info
        api_key: OpenWeatherMap API key (required for Canada stadiums)
    
    Returns:
        Dictionary with parsed weather data
    """
    latitude = stadium.get('latitude')
    longitude = stadium.get('longitude')
    api_choice = get_weather_api_for_stadium(stadium)
    
    if api_choice == "OPENWEATHERMAP":
        if not api_key:
            print(f"ERROR: OpenWeatherMap API key required for {stadium.get('team_name')}")
            return {}
        
        weather_data = get_openweathermap_weather(latitude, longitude, api_key)
        return parse_openweathermap_weather_data(weather_data)
    
    else:  # NWS
        weather_data = get_nws_weather(latitude, longitude)
        return parse_nws_weather_data(weather_data)
