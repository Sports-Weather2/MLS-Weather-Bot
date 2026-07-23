# Changelog

## [1.0.0] - July 23, 2026

### Added
- Initial MLS Weather Bot setup
- All 30 teams configured with coordinates
- GitHub Actions workflows (3 schedules)
- Python script stubs
- Slack integration framework

### Design Specifications
- Alert thresholds: HIGH RISK ≥80%, MONITOR 35-79%, CLEAR <35%
- Roofed stadiums: Atlanta, Houston, Vancouver (auto-filtered)
- Delay probability tiers: VERY HIGH, HIGH, ELEVATED
- Real-time monitoring: Every 10 minutes during games
- Data sources: NWS API (weather), ESPN/MLS API (schedule)

### Status
- Phase 1: GitHub repository structure complete
- Phase 2: Alert logic implementation (upcoming)
- Phase 3: Testing and validation (upcoming)
- Launch: March 1, 2027
