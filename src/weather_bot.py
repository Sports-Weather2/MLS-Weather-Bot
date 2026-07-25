def get_game_schedule():
    """Fetch today's MLS game schedule from ESPN API (PT timezone)."""
    try:
        # Get today's date in PT
        pt_tz = pytz.timezone('America/Los_Angeles')
        today_pt = datetime.now(pt_tz).date()
        print(f"🕐 Today's date (PT): {today_pt}")
        
        response = requests.get(
            "https://site.api.espn.com/apis/site/v2/sports/soccer/usa.1/scoreboard",
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
        
        events = data.get("events", [])
        print(f"📊 Total events from API: {len(events)}")
        
        games_today = []
        
        for idx, event in enumerate(events):
            # Parse event date and convert to PT
            date_str = event.get("date", "")
            if date_str:
                try:
                    # Parse ISO format date: "2026-07-25T19:30Z"
                    event_dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                    event_date_pt = event_dt.astimezone(pt_tz).date()
                    
                    # Debug: print first 5 events
                    if idx < 5:
                        competitors = event.get("competitors", [])
                        home = "?"
                        away = "?"
                        if len(competitors) >= 2:
                            for comp in competitors:
                                if comp.get("homeAway") == "home":
                                    home = comp.get("team", {}).get("displayName", "?")
                                elif comp.get("homeAway") == "away":
                                    away = comp.get("team", {}).get("displayName", "?")
                        print(f"  Event {idx}: {away} @ {home} on {event_date_pt} (UTC: {event_dt.date()}) - Match: {event_date_pt == today_pt}")
                    
                    # Only include games from today (PT)
                    if event_date_pt != today_pt:
                        continue
                except Exception as e:
                    print(f"  Error parsing event {idx}: {e}")
                    continue
            
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
        
        print(f"✅ Found {len(games_today)} games for today (PT)")
        return games_today
    except Exception as e:
        print(f"Error fetching game schedule: {e}")
        import traceback
        traceback.print_exc()
        return []
