import os
import requests
import json
from datetime import datetime, timedelta
import pytz
from src.utils import (
    get_weather_for_stadium,
    get_risk_level,
    get_delay_probability,
    get_air_quality,
    get_aqi_category,
)

SLACK_WEBHOOK_URL = os.getenv('SLACK_WEBHOOK_URL')
OPENWEATHERMAP_API_KEY = os.getenv('OPENWEATHERMAP_API_KEY')
ESPN_MLS_SCOREBOARD = 'https://site.api.espn.com/apis/site/v2/sports/soccer/usa.1/scoreboard'

with open('config/mls_stadiums.json', 'r') as f:
    STADIUMS = json.load(f)

PT = pytz.timezone('America/Los_Angeles')


def get_mls_games_for_date(target_date=None):
    """Fetch MLS games for a specific date using ESPN dates parameter."""
    try:
        if target_date is None:
            target_date = datetime.now(PT).date()
        
        date_str = target_date.strftime('%Y%m%d')
        url = f"{ESPN_MLS_SCOREBOARD}?dates={date_str}"
        
        print(f"Line 1: Fetching games for {date_str}: {url}")
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if 'events' in data:
            games = data['events']
            print(f"Line 2: Found {len(games)} games on {date_str}")
            return games
        else:
            print(f"Line 3: No 'events' key in response")
            return []
    
    except Exception as e:
        print(f"Line 4: Error fetching games: {e}")
        import traceback
        traceback.print_exc()
        return []


def get_next_scheduled_game():
    """Find next scheduled game using competitors array."""
    try:
        tomorrow = datetime.now(PT).date() + timedelta(days=1)
        end_date = tomorrow + timedelta(days=13)
        
        start_str = tomorrow.strftime('%Y%m%d')
        end_str = end_date.strftime('%Y%m%d')
        date_range = f"{start_str}-{end_str}"
        
        url = f"{ESPN_MLS_SCOREBOARD}?dates={date_range}"
        print(f"Line 5: Fetching next 14 days: {url}")
        
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        events = data.get('events', [])
        print(f"Line 6: Total events in range: {len(events)}")
        
        if not events:
            print("Line 7: No events found")
            return None
        
        for idx, event in enumerate(events):
            try:
                if 'competitions' not in event:
                    continue
                
                comp = event['competitions'][0]
                competitors = comp.get('competitors', [])
                
                home_competitor = next((c for c in competitors if c.get('homeAway') == 'home'), None)
                away_competitor = next((c for c in competitors if c.get('homeAway') == 'away'), None)
                
                if not home_competitor or not away_competitor:
                    continue
                
                home_team = home_competitor.get('team', {}).get('displayName', '')
                away_team = away_competitor.get('team', {}).get('displayName', '')
                
                if not home_team or not away_team:
                    continue
                
                date_str = event.get('date', '')
                if not date_str:
                    continue
                
                game_date_utc = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                game_date_pt = game_date_utc.astimezone(PT)
                
                formatted_date = game_date_pt.strftime('%A, %B %d')
                formatted_time = game_date_pt.strftime('%I:%M %p PT').lstrip('0')
                
                print(f"Line 8: Found valid game: {away_team} @ {home_team}")
                
                return {
                    'date': formatted_date,
                    'time': formatted_time,
                    'home_team': home_team,
                    'away_team': away_team
                }
            
            except Exception as e:
                continue
        
        print("Line 9: No valid games found after checking all events")
        return None
    
    except Exception as e:
        print(f"Line 10: Error: {e}")
        import traceback
        traceback.print_exc()
        return None


def post_no_games_message():
    """Post All Clear message for NO-GAMES DAYS with next match info to #mls-gameday-weather."""
    try:
        print("Line 16: No games today - posting off-day message to #mls-gameday-weather")
        
        next_game = get_next_scheduled_game()
        
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "⚽ MLS Daily Weather Report",
                    "emoji": True
                }
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "✅ *No games scheduled today*"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "MLS Weather Bot is monitoring and will alert on the next game day."
                }
            },
            {"type": "divider"}
        ]
        
        # ONLY show next match on no-games days
        if next_game:
            next_match_text = f"🏟️ *Next Match:* {next_game['away_team']} @ {next_game['home_team']}\n{next_game['date']} @ {next_game['time']}"
        else:
            next_match_text = "🏟️ *Next Match:* TBD"
        
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": next_match_text
            }
        })
        
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"Updated: {datetime.now(PT).strftime('%b %d at %I:%M %p PT')}"
                }
            ]
        })
        
        message = {"blocks": blocks}
        response = requests.post(SLACK_WEBHOOK_URL, json=message, timeout=10)
        response.raise_for_status()
        print(f"Line 17: Off-day message posted to #mls-gameday-weather")
        
    except Exception as e:
        print(f"Line 18: Error posting off-day message: {e}")
        import traceback
        traceback.print_exc()


def post_gameday_dashboard(games):
    """Post gameday dashboard with summary overview."""
    try:
        print(f"Line 13: Processing {len(games)} games for dashboard")
        
        high_risk_count = 0
        monitor_count = 0
        clear_count = 0
        
        high_risk_games = []
        wind_concerns = []
        rain_concerns = []
        high_aqi_stadiums = []
        temp_extremes = []
        earliest_game = None
        latest_game = None
        
        for idx, game in enumerate(games):
            try:
                print(f"Line 14.{idx}: Processing game...")
                
                if not isinstance(game, dict) or 'competitions' not in game:
                    continue
                
                comp = game['competitions'][0]
                competitors = comp.get('competitors', [])
                
                if not competitors or len(competitors) < 2:
                    continue
                
                home_competitor = next((c for c in competitors if c.get('homeAway') == 'home'), None)
                away_competitor = next((c for c in competitors if c.get('homeAway') == 'away'), None)
                
                if not home_competitor or not away_competitor:
                    continue
                
                home_team = home_competitor.get('team', {}).get('displayName', '')
                away_team = away_competitor.get('team', {}).get('displayName', '')
                
                if not home_team or not away_team:
                    continue
                
                date_str = game.get('date', '')
                if not date_str:
                    continue
                
                try:
                    game_date_utc = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                    game_date_pt = game_date_utc.astimezone(PT)
                    game_time_pt = game_date_pt.strftime('%I:%M %p PT').lstrip('0')
                except Exception as e:
                    print(f"Line 14.{idx}g: Error parsing date {date_str}: {e}")
                    continue
                
                # Track earliest and latest games
                if earliest_game is None:
                    earliest_game = (away_team, home_team, game_time_pt)
                latest_game = (away_team, home_team, game_time_pt)
                
                venue_name = comp.get('venue', {}).get('fullName', 'Unknown Stadium')
                
                stadium_config = next((s for s in STADIUMS if s['stadium'] == venue_name), None)
                
                if not stadium_config:
                    stadium_config = next((s for s in STADIUMS if home_team in s.get('teams', [])), None)
                    if not stadium_config:
                        continue
                
                weather = get_weather_for_stadium(stadium_config)
                if not weather:
                    continue
                
                lat = stadium_config.get('latitude')
                lon = stadium_config.get('longitude')
                air_quality_data = get_air_quality(lat, lon)
                
                air_quality_info = {}
                if air_quality_data:
                    aqi_cat = get_aqi_category(air_quality_data['aqi'])
                    air_quality_info = {
                        'aqi': air_quality_data['aqi'],
                        'category': aqi_cat['category'],
                        'emoji': aqi_cat['emoji'],
                        'pm25': air_quality_data['pm25'],
                    }
                
                risk_level, why_triggered = get_risk_level(weather, stadium_config)
                delay_prob = get_delay_probability(risk_level, weather)
                
                # Count risk levels
                if risk_level == 'HIGH RISK':
                    high_risk_count += 1
                    high_risk_games.append(f"{away_team} @ {home_team}")
                elif risk_level == 'MONITOR':
                    monitor_count += 1
                else:
                    clear_count += 1
                
                # Collect concerns for summary
                temp = weather.get('temperature', 0)
                rain = weather.get('rain_probability', 0)
                wind = weather.get('wind_speed', 0)
                conditions = weather.get('conditions', '')
                
                if rain >= 35:
                    rain_concerns.append(f"{away_team} @ {home_team} ({rain}%)")
                
                if wind >= 20:
                    wind_concerns.append(f"{away_team} @ {home_team} ({wind} mph)")
                
                if temp <= 35 or temp >= 95:
                    temp_extremes.append(f"{away_team} @ {home_team} ({temp}°F)")
                
                if air_quality_info and air_quality_info.get('aqi', 0) >= 150:
                    high_aqi_stadiums.append(f"{away_team} @ {home_team} (AQI {air_quality_info['aqi']})")
                
                print(f"Line 14.{idx}z: ✅ Processed: {away_team} @ {home_team}")
            
            except Exception as e:
                print(f"Line 14.{idx}ERROR: {e}")
                import traceback
                traceback.print_exc()
                continue
        
        print(f"\nLine 15: Successfully analyzed {len(games)} games")
        
        total_games = high_risk_count + monitor_count + clear_count
        if total_games == 0:
            print("Line 16: No valid game data, posting no games message")
            post_no_games_message()
            return
        
        # Build dashboard message
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "⚽ MLS Daily Weather Report",
                    "emoji": True
                }
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "📊 *TODAY'S OVERVIEW*"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"🎮 *Games Scheduled:* {total_games}\n🔴 *High-Risk:* {high_risk_count} games\n🟡 *Monitor:* {monitor_count} games\n🟢 *Clear:* {clear_count} games"
                }
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "⛅ *WEATHER SUMMARY*"
                }
            }
        ]
        
        # Weather summary
        weather_summary = ""
        if rain_concerns:
            weather_summary += f"💧 Rain expected: {len(rain_concerns)} stadiums\n"
        else:
            weather_summary += f"☀️ Rain: None significant\n"
        
        if wind_concerns:
            weather_summary += f"💨 Wind concerns: {len(wind_concerns)} stadiums (20+ mph)\n"
        else:
            weather_summary += f"💨 Wind: Light and manageable\n"
        
        if temp_extremes:
            weather_summary += f"🌡️ Extreme temps: {len(temp_extremes)} stadiums\n"
        else:
            weather_summary += f"🌡️ Temperature: Moderate range\n"
        
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": weather_summary
            }
        })
        
        # Air quality summary
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "💨 *AIR QUALITY ALERT*"
            }
        })
        
        if high_aqi_stadiums:
            aqi_text = f"⚠️ *AQI 150+ at {len(high_aqi_stadiums)} stadiums (Unhealthy)*\n"
            aqi_text += f"✅ Normal AQI at {total_games - len(high_aqi_stadiums)} stadiums"
        else:
            aqi_text = f"✅ *All stadiums have healthy air quality*"
        
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": aqi_text
            }
        })
        
        # Monitoring window - UPDATED LOGIC FOR SINGLE GAME
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "⏱️ *MONITORING WINDOW*"
            }
        })
        
        if earliest_game and latest_game:
            if total_games == 1:
                # Single game - only show game time once
                earliest_info = f"{earliest_game[0]} @ {earliest_game[1]} ({earliest_game[2]})"
                monitoring_text = f"🎬 *Match:* {earliest_info}\n🚨 *Real-time monitoring:* 10 AM - 10 PM PT"
            else:
                # Multiple games - show first and last
                earliest_info = f"{earliest_game[0]} @ {earliest_game[1]} ({earliest_game[2]})"
                latest_info = f"{latest_game[0]} @ {latest_game[1]} ({latest_game[2]})"
                monitoring_text = f"🎬 *First game:* {earliest_info}\n📍 *Last game:* {latest_info}\n🚨 *Real-time monitoring:* 10 AM - 10 PM PT"
        else:
            monitoring_text = "🚨 *Real-time monitoring:* 10 AM - 10 PM PT"
        
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": monitoring_text
            }
        })
        
        # Action items
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "📋 *ACTION ITEMS*"
            }
        })
        
        action_text = ""
        if high_risk_count > 0:
            action_text += f"• ⚠️ Check #mls-high-risk-alerts at 10 AM for {high_risk_count} HIGH RISK game(s)\n"
            action_text += f"• Extend daypart windows for HIGH RISK games\n"
        else:
            action_text += f"• ✅ No HIGH RISK games — standard scheduling\n"
        
        if high_aqi_stadiums:
            action_text += f"• Monitor air quality at {len(high_aqi_stadiums)} stadium(s) throughout day\n"
        
        if wind_concerns or rain_concerns:
            action_text += f"• Have contingency plans ready for weather developments\n"
        
        action_text += f"• Monitor real-time alerts during 10 AM - 10 PM PT window"
        
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": action_text
            }
        })
        
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"Updated: {datetime.now(PT).strftime('%b %d at %I:%M %p PT')}"
                }
            ]
        })
        
        message = {"blocks": blocks}
        response = requests.post(SLACK_WEBHOOK_URL, json=message, timeout=10)
        response.raise_for_status()
        print(f"Line 19: Dashboard posted to Slack")
        
    except Exception as e:
        print(f"Line 20: Error posting report: {e}")
        import traceback
        traceback.print_exc()


def main():
    """Main function."""
    try:
        print("Line 0: Starting weather_bot.py")
        today_games = get_mls_games_for_date()
        
        # NO GAMES SCHEDULED - POST OFF-DAY MESSAGE WITH NEXT MATCH INFO TO #mls-gameday-weather
        if not today_games or len(today_games) == 0:
            print("Line X: No games today - posting off-day message to #mls-gameday-weather")
            post_no_games_message()
            return
        
        # GAMES EXIST - POST FULL DASHBOARD TO #mls-gameday-weather
        print("Line Y: Games found - posting weather dashboard")
        post_gameday_dashboard(today_games)
    
    except Exception as e:
        print(f"Line Z: Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
else:
    main()
