#!/usr/bin/env python3
"""
MLS High-Risk Weather Alert
Disabled - only real-time delay monitor posts alerts.
This exists as a placeholder for potential future high-risk pre-game warnings.
"""

import os
import sys
import logging
from datetime import datetime, timezone

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Get current time in PT
now_utc = datetime.now(timezone.utc)
now_pt = now_utc.astimezone()
logger.info(f"Current PT time: {now_pt.strftime('%Y-%m-%d %H:%M:%S %Z')}")

def main():
    """Placeholder - all alerts via real-time delay monitor."""
    logger.info("=" * 60)
    logger.info("MLS High-Risk Weather Alert - placeholder (disabled)")
    logger.info("Alerts posted by: Real-Time Delay Monitor (12-8 PM PT)")
    logger.info("=" * 60)


if __name__ == '__main__':
    main()
