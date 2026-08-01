**Correct Prediction = either:**
- ✅ HIGH RISK alert posted AND game was delayed/postponed
- ✅ No HIGH RISK alert posted AND game played on time (even if MONITOR level)

**Incorrect Prediction = either:**
- ❌ HIGH RISK alert posted BUT game played on time
- ❌ No HIGH RISK alert posted BUT game was delayed/postponed

---

## Next Review Schedule

**Automatic reviews continue daily at 8:00 AM PT.**

| Date | Action | Responsible |
|------|--------|-------------|
| 2026-08-02 | Review 1-game day (NE vs Houston) performance | System (automatic) |
| 2026-08-03 | Confirm off-day behavior (no games) | System (automatic) |
| 2026-08-15 | Compare HIGH RISK predictions vs 13-game day delays | System (automatic) |
| 2026-08-30 | Monthly accuracy review + threshold assessment | Manual review |

---

## Data Integrity Notes

- **Timestamps:** All times displayed in PT (Pacific Time) for consistency
- **ESPN Delays:** Detected via `status.type == 'STATUS_SCHEDULED_POSTPONED'` or `status.period == 0` with delay minutes
- **Slack Parsing:** Reads message timestamps and alert emoji to match with games
- **Time Zone Handling:** Cron schedules in UTC (0 14 * * *, 0 15 * * *, 0 17 * * *) converted to PT display
- **Missing Data:** If ESPN API unavailable, marked as "Data unavailable" — does not affect accuracy calculation

---

## Files & Functions

**Automation files:**
- `src/analytics.py` — Slack parser + ESPN delay checker + file updater
- `.github/workflows/analytics-update.yml` — Triggers `analytics.py` daily at 8 AM PT

**Supporting files:**
- `src/weather_bot.py` — Populates `#mls-gameday-weather` at 7 AM PT
- `src/high_risk_alert.py` — Populates `#mls-high-risk-alerts` at 10 AM PT
- `src/mls_status_monitor.py` — Game status message at 7 AM PT

---

Last updated: August 01, 2026 05:45 AM PT (automatic) | Next automatic update: August 02, 2026 08:00 AM PT | Workflow: `analytics-update.yml`
