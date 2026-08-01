def post_no_games_message():
    """Post no games message with next match if available."""
    try:
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
                    "text": "📊 *TODAY'S OVERVIEW*"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "🎮 *Games Scheduled:* 0\n✅ *System Status:* Active & Monitoring"
                }
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "⏱️ *MONITORING WINDOW*"
                }
            }
        ]
        
        if next_game:
            monitoring_text = f"📅 *Next Match:* {next_game['away_team']} @ {next_game['home_team']}\n📍 {next_game['date']} @ {next_game['time']}"
        else:
            monitoring_text = "📅 *Next Match:* TBD"
        
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": monitoring_text
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
        print("Line 11: No games message posted to Slack")
        
    except Exception as e:
        print(f"Line 12: Error posting no games message: {e}")
        import traceback
        traceback.print_exc()
