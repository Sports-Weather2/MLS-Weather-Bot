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
