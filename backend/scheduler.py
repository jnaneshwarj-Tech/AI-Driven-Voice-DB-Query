"""
scheduler.py — APScheduler-based automatic database backup.

Schedule:
  - Daily backup at midnight (configurable)
  - Weekly backup on Sundays at 01:00

This module is imported by main.py and started in the lifespan context.
Includes graceful fallback if apscheduler is not installed.
"""

import logging

logger = logging.getLogger("uvicorn.error")

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    APSCHEDULER_AVAILABLE = True
except ImportError:
    BackgroundScheduler = None
    CronTrigger = None
    APSCHEDULER_AVAILABLE = False
    logger.warning("[Scheduler] apscheduler package not found. Automatic scheduled backups will be disabled until installed ('pip install apscheduler').")

_scheduler = None


def _run_daily_backup():
    """Called by scheduler for daily automatic backup."""
    try:
        from routes_backup import create_backup_internal
        result = create_backup_internal(backup_type="auto_daily", created_by="scheduler")
        if result.get("success"):
            logger.info(f"[Scheduler] Daily backup completed: {result.get('backup_name')} ({result.get('size_bytes', 0):,} bytes)")
        else:
            logger.error(f"[Scheduler] Daily backup FAILED: {result.get('error')}")
    except Exception as e:
        logger.error(f"[Scheduler] Daily backup exception: {e}")


def _run_weekly_backup():
    """Called by scheduler for weekly automatic backup."""
    try:
        from routes_backup import create_backup_internal
        result = create_backup_internal(backup_type="auto_weekly", created_by="scheduler")
        if result.get("success"):
            logger.info(f"[Scheduler] Weekly backup completed: {result.get('backup_name')}")
        else:
            logger.error(f"[Scheduler] Weekly backup FAILED: {result.get('error')}")
    except Exception as e:
        logger.error(f"[Scheduler] Weekly backup exception: {e}")


def start_scheduler():
    """
    Start the APScheduler.
    Safe to call multiple times — starts only once.
    """
    global _scheduler

    if not APSCHEDULER_AVAILABLE:
        print("[Scheduler] WARNING: apscheduler not installed. Scheduled backups disabled. Run 'pip install apscheduler'.")
        return

    try:
        from config import settings
        if not settings.BACKUP_AUTO_ENABLED:
            logger.info("[Scheduler] Auto-backup disabled via config.")
            return

        if _scheduler and _scheduler.running:
            logger.info("[Scheduler] Already running, skipping restart.")
            return

        _scheduler = BackgroundScheduler(
            daemon=True,
            job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 3600}
        )

        # Daily at midnight
        _scheduler.add_job(
            _run_daily_backup,
            trigger=CronTrigger(hour=0, minute=0),
            id="daily_backup",
            replace_existing=True,
        )

        # Weekly on Sunday at 01:00
        _scheduler.add_job(
            _run_weekly_backup,
            trigger=CronTrigger(day_of_week="sun", hour=1, minute=0),
            id="weekly_backup",
            replace_existing=True,
        )

        _scheduler.start()
        logger.info("[Scheduler] Auto-backup scheduler started. Daily at 00:00, Weekly on Sunday at 01:00.")

    except Exception as e:
        logger.error(f"[Scheduler] Failed to start scheduler: {e}")


def stop_scheduler():
    """Stop the scheduler gracefully on app shutdown."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("[Scheduler] Stopped.")
