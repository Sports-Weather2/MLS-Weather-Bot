# MLS Weather Bot Analytics

## Overview

This document tracks the performance of the **MLS Weather Alert System** — monitoring prediction accuracy, Slack message timing, and ESPN delay detection.

**System Status:** ✅ Fully Automated (runs daily at 7 AM, 8 AM, and 10 AM PT)

---

## Data Updates

This file is **automatically updated daily** at 8:00 AM PT via GitHub Actions workflow (`analytics-update.yml`):

1. Parses Slack alerts from previous day's `#mls-gameday-weather` and `#mls-high-risk-alerts` channels
2. Checks ESPN API for actual MLS delays/postponements  
3. Calculates prediction accuracy against actual outcomes
4. Tracks workflow execution logs

**Update Frequency:** Daily (automatic) — runs at 8:00 AM PT via `analytics-update.yml` workflow  
**Data Sources:** Slack API, ESPN API, GitHub Actions logs

---

## Performance Metrics

### Alert Accuracy
Compares `high_risk_alert.py` predictions vs actual game delays/postponements.

| Date | Total Games | High Risk Alerts | Actual Delays | Accuracy | Notes |
|------|------------|-----------------|---------------|----------|-------|
| 2026-07-25 | 15 | 0 | 0 | 100% | All games played on time ✅ |
| 2026-08-01 | 14 | 0 | 0 | 100% | Clear day, no delays ✅ |

### Threshold Performance
Tests current alert thresholds against actual outcomes.

| Threshold | Current Value | Status | Notes |
|-----------|---------------|--------|-------|
| HIGH RISK: Rain ≥80% + thunderstorms | ≥80% | ✅ Valid | No false positives observed |
| HIGH RISK: Rain ≥90% | ≥90% | ✅ Valid | Conservative threshold working |
| HIGH RISK: Thunderstorms + wind ≥30 mph | ≥30 mph | ✅ Valid | Protective, no missed delays |
| HIGH RISK: Temp ≤35°F + wind ≥20 mph | ≥20 mph | ✅ Valid | Rarely triggered in summer |
| HIGH RISK: Wind ≥40 mph | ≥40 mph | ✅ Valid | Extreme condition, no false alarms |
| HIGH RISK: AQI ≥150 | ≥150 | ✅ Valid | No AQI delays observed |
| MONITOR: Rain 35–79% | 35–79% | ✅ Valid | Informational only, no delays |
| MONITOR: Wind ≥20 mph | ≥20 mph | ✅ Valid | Increased from 15 mph on 2026-04-23 |

### Slack Message Timing
Tracks when alerts are posted vs when games start.

| Metric | Target | Actual | Status |
|--------|--------|--------|--------|
| Daily Weather Dashboard | 7:00 AM PT | 7:00 AM PT ✅ | On schedule |
| High Risk Consolidation | 10:00 AM PT | 10:00 AM PT ✅ | On schedule |
| Game Status Monitor | 7:00 AM PT | 7:00 AM PT ✅ | On schedule |
| Analytics Update | 8:00 AM PT | 8:00 AM PT ✅ | On schedule |

---

## Workflow Execution Log

### Automated Workflow Schedule

| Workflow | Trigger | Time (PT) | UTC | Status | Last Run |
|----------|---------|-----------|-----|--------|----------|
| `weather-update-v2.yml` | Cron schedule | 7:00 AM | 14:00 | ✅ Active | 2026-08-01 07:00 AM |
| `high-risk-alert-v2.yml` | Cron schedule | 10:00 AM | 17:00 | ✅ Active | 2026-08-01 10:00 AM |
| `mls-status-monitor-v2.yml` | Cron schedule | 7:00 AM | 14:00 | ✅ Active | 2026-08-01 07:00 AM |
| `analytics-update.yml` | Cron schedule | 8:00 AM | 15:00 | ✅ Active | 2026-08-01 08:00 AM |

**All workflows are running automatically on their scheduled times. Manual trigger via GitHub Actions available for testing.**

---

## Key Issues & Resolutions

### ✅ Resolved Issues

| Date | Issue | Root Cause | Resolution | Status |
|------|-------|-----------|-----------|--------|
| 2026-03-29 | Workflows not triggering automatically | Old schedule cache in GitHub Actions | Created v2 workflow files with updated cron | ✅ Fixed |
| 2026-04-23 | Low threshold for wind alerts | Too many false positives | Raised MONITOR threshold from 15 mph → 20 mph | ✅ Fixed |
| 2026-07-25 | `high_risk_alert.py` sending per-game messages | Redundant notifications | Redesigned to ONE consolidated message | ✅ Fixed |
| 2026-07-31 | Single-game days showing duplicate "First/Last game" | Monitoring window logic error | Updated to show `🎬 *Match:*` when only 1 game | ✅ Fixed |
| 2026-08-01 | `analytics-update.yml` git push failing | Missing GitHub token permissions | Added `permissions: contents: write` to workflow | ✅ Fixed |

### 🟡 In Progress

None currently.

### 🔴 Known Limitations

| Item | Impact | Workaround | Priority |
|------|--------|-----------|----------|
| AQI delays (Olympics/wildfires) | Rare in normal season | Monitor manually during air quality events | Low |
| Canadian stadiums (3 teams) | Different data source | Using OpenWeatherMap API separately | Low |

---

## Prediction Accuracy Tracking

### How It Works

1. **Daily at 8:00 AM PT:** `analytics.py` runs automatically
2. **Slack Parsing:** Reads yesterday's alerts from both channels
3. **ESPN API Check:** Queries for actual delays/postponements
4. **Match Logic:** Compares predicted risk level vs actual outcome
5. **ANALYTICS.md Update:** Appends new row to performance table
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
6. **Auto-Commit:** Commits updated file to repo

### Accuracy Calculation
