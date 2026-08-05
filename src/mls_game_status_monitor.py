import os
import json
import requests
from datetime import datetime, timedelta
import pytz
from src.utils import get_weather_for_stadium, get_risk_level, get_air_quality

# ESPN API endpoints
ESPN_MLS_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/soccer/usa.1/scoreboard"
ESPN_LEAGUES_CUP_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/soccer/concacaf.leagues.cup/scoreboard"

# Slack webhook
SLACK_WEBHOOK_URL_HIGH_RISK = os.getenv("SLACK_WEBHOOK_URL_HIGH_RISK")

# PT timezone
PT = pytz.timezone("America/Los_Angeles")

# Game state constants
STATE_DELAYED = "DELAYED"
STATE_POSTPONED = "POSTPONED"
STATE_SUSPENDED = "SUSPENDED"
STATE_RESUMED = "RESUMED"
STATE_LIVE = "LIVE"
STATE_FINAL = "FINAL"

# State cache file
STATE_CACHE_FILE = "mls_game_states.json"

def load_stadiums():
    """Load stadium configuration"""
    config_path = os.path.join(os.path.dirname(__file__), "..", "config", "mls_stadiums.json")
    with open(config_path, "r") as f:
        return json.load(f)

def get_stadium_by_team(stadiums, team_name):
    """Find stadium by team name"""
    for stadium in stadiums:
        if any(team_name.lower() in t.lower() for t in stadium.get("teams", [])):
            return stadium
    return None

def is_leagues_cup_match(event):
    """Check if match is Leagues Cup"""
    if not event or "competitions" not in event:
        return False
    competition = event.get("competitions", [{}])[0]
    comp_name = competition.get("name", "").lower()
    return "leagues cup" in comp_name

def load_state_cache():
    """Load game state cache"""
    try:
        if os.path.exists(STATE_CACHE_FILE):
            with open(STATE_CACHE_FILE, "r") as f:
                return json.load(f)
    except Exception as e:
        print(f"Error loading state cache: {str(e)}")
    return {}

def save_state_cache(cache):
    """Save game state cache"""
    try:
        with open(STATE_CACHE_FILE, "w") as f:
            json.dump(cache, f, indent=2)
    except Exception as e:
        print(f"Error saving state cache: {str(e)}")

def get_game_state(competition):
    """Extract game state from competition"""
    status = competition.get("status", {}).get("type", "").upper()
    
    if "DELAYED" in status:
        return STATE_DELAYED
    elif "POSTPONED" in status:
        return STATE_POSTPONED
    elif "SUSPENDED" in status:
        return STATE_SUSPENDED
    elif "LIVE" in status or "IN_PROGRESS" in status:
        return STATE_LIVE
    elif "FINAL" in status:
        return STATE_FINAL
    else:
        return status

def post_to_slack(message):
    """Post message to Slack"""
    payload = {"text": message}
    try:
        response = requests.post(SLACK_WEBHOOK_URL_HIGH_RISK, json=payload)
        return response.status_code == 200
    except Exception as e:
        print(f"Error posting to Slack: {str(e)}")
        return False

def get_delay_reason(competition, stadium):
    """Extract delay reason from competition"""
    status_desc = competition.get("status", {}).get("detail", "").lower()
    notes = competition.get("notes", [])
    
    weather_keywords = ['rain', 'weather', 'storm', 'lightning', 'inclement', 'wind', 'snow', 'fog', 'thunder']
    
    # Check status description
    for keyword in weather_keywords:
        if keyword in status_desc:
            return f"⚠️ Weather-related: {status_desc}"
    
    # Check notes
    if notes:
        note_text = " ".join([n.get("headline", "") for n in notes]).lower()
        for keyword in weather_keywords:
            if keyword in note_text:
                return f"⚠️ Weather-related delay"
    
    return "⏸️ Delay reason not yet specified"

def main():
    """Main function - monitor game status changes"""
    try:
        today = datetime.now(PT).date()
        date_str = today.strftime("%Y%m%d")
        
        stadiums = load_stadiums()
        state_cache = load_state_cache()
        
        # Fetch MLS games
        try:
            mls_response = requests.get(
                f"{ESPN_MLS_SCOREBOARD}?dates={date_str}",
                timeout=10
            )
            mls_data = mls_response.json() if mls_response.status_code == 200 else {"events": []}
        except Exception as e:
            print(f"MLS API Error: {str(e)}")
            mls_data = {"events": []}
        
        # Fetch Leagues Cup games
        try:
            lc_response = requests.get(
                f"{ESPN_LEAGUES_CUP_SCOREBOARD}?dates={date_str}",
                timeout=10
            )
            lc_data = lc_response.json() if lc_response.status_code == 200 else {"events": []}
        except Exception as e:
            print(f"Leagues Cup API Error: {str(e)}")
            lc_data = {"events": []}
        
        # Combine events
        all_events = mls_data.get("events", []) + lc_data.get("events", [])
        
        alerts_posted = []
        
        # Monitor each game
        for event in all_events:
            try:
                event_id = event.get("id")
                competition = event.get("competitions", [{}])[0]
                competitors = competition.get("competitors", [])
                
                if len(competitors) < 2:
                    continue
                
                home_team = competitors[0]["team"]["displayName"]
                away_team = competitors[1]["team"]["displayName"]
                
                game_time_str = competition.get("startDate", "")
                if not game_time_str:
                    continue
                
                try:
                    game_time = datetime.fromisoformat(game_time_str.replace("Z", "+00:00"))
                    game_time_pt = game_time.astimezone(PT)
                except:
                    continue
                
                # Get current state
                current_state = get_game_state(competition)
                previous_state = state_cache.get(event_id, "SCHEDULED")
                
                # Check if Leagues Cup
                is_lc = is_leagues_cup_match(event)
                lc_header = "🏆 LEAGUES CUP" if is_lc else "⚽ MLS"
                
                # Alert on state changes (priority order)
                if current_state == STATE_POSTPONED and previous_state != STATE_POSTPONED:
                    message = f"{lc_header} - 🚨 *GAME POSTPONED*\n\n"
                    message += f"*{away_team}* @ *{home_team}*\n"
                    message += f"⏰ Originally scheduled: {game_time_pt.strftime('%I:%M %p PT')}\n"
                    message += f"📍 Status: POSTPONED\n\n"
                    message += f"{get_delay_reason(competition, None)}\n\n"
                    message += "📞 Contact venue for rescheduling details"
                    
                    post_to_slack(message)
                    alerts_posted.append(f"POSTPONED: {away_team} @ {home_team}")
                
                elif current_state == STATE_SUSPENDED and previous_state != STATE_SUSPENDED:
                    message = f"{lc_header} - ⏸️ *GAME SUSPENDED*\n\n"
                    message += f"*{away_team}* @ *{home_team}*\n"
                    message += f"⏰ Time: {game_time_pt.strftime('%I:%M %p PT')}\n"
                    message += f"📍 Status: SUSPENDED (in-play)\n\n"
                    message += f"{get_delay_reason(competition, None)}\n\n"
                    message += "🔔 Monitoring for resumption"
                    
                    post_to_slack(message)
                    alerts_posted.append(f"SUSPENDED: {away_team} @ {home_team}")
                
                elif current_state == STATE_DELAYED and previous_state != STATE_DELAYED:
                    message = f"{lc_header} - ⏳ *GAME DELAYED*\n\n"
                    message += f"*{away_team}* @ *{home_team}*\n"
                    message += f"⏰ Originally scheduled: {game_time_pt.strftime('%I:%M %p PT')}\n"
                    message += f"📍 Status: DELAYED\n\n"
                    message += f"{get_delay_reason(competition, None)}\n\n"
                    message += "🔔 Monitoring for kickoff update"
                    
                    post_to_slack(message)
                    alerts_posted.append(f"DELAYED: {away_team} @ {home_team}")
                
                elif current_state == STATE_RESUMED and previous_state == STATE_SUSPENDED:
                    message = f"{lc_header} - ▶️ *GAME RESUMED*\n\n"
                    message += f"*{away_team}* @ *{home_team}*\n"
                    message += f"✅ Play has resumed — match now LIVE"
                    
                    post_to_slack(message)
                    alerts_posted.append(f"RESUMED: {away_team} @ {home_team}")
                
                # Update cache with current state
                state_cache[event_id] = current_state
                
            except Exception as e:
                print(f"Error processing game: {str(e)}")
                continue
        
        # Save updated cache
        save_state_cache(state_cache)
        
        if alerts_posted:
            print(f"✅ Posted {len(alerts_posted)} alert(s): {', '.join(alerts_posted)}")
        else:
            print("✅ No status changes detected")
        
    except Exception as e:
        print(f"❌ Main error: {str(e)}")
        post_to_slack(f"❌ Game Status Monitor Error: {str(e)}")

if __name__ == "__main__":
    main()
