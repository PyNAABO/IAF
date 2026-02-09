import redis
import json
import logging
import random
from datetime import datetime, timedelta
from .config import (
    REDIS_URL,
    SCHEDULE_INTERVAL_MIN_HOURS,
    SCHEDULE_INTERVAL_MAX_HOURS,
    PROCESSED_USER_EXPIRY_DAYS,
    BLACKOUT_START_HOUR,
    BLACKOUT_END_HOUR,
    get_random_schedule_hours,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def get_redis_client():
    """Connects to Redis using the URL from config."""
    if not REDIS_URL:
        return None
    try:
        return redis.from_url(
            REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        return None


def save_cookies(username, cookies):
    """Saves Playwright cookies to Redis."""
    r = get_redis_client()
    if not r:
        return False
    try:
        r.set(f"session:{username}", json.dumps(cookies))
        logger.info(f"Cookies saved for user: {username}")
        return True
    except Exception as e:
        logger.error(f"Failed to save cookies: {e}")
        return False


def load_cookies(username):
    """Loads Playwright cookies from Redis."""
    r = get_redis_client()
    if not r:
        return []
    try:
        data = r.get(f"session:{username}")
        if data:
            return json.loads(data)
    except Exception as e:
        logger.error(f"Failed to load cookies: {e}")
    return []


def is_in_blackout_hours():
    """Check if current time is in blackout hours (10PM-5AM)."""
    current_hour = datetime.now().hour
    if BLACKOUT_START_HOUR > BLACKOUT_END_HOUR:
        return current_hour >= BLACKOUT_START_HOUR or current_hour < BLACKOUT_END_HOUR
    return BLACKOUT_START_HOUR <= current_hour < BLACKOUT_END_HOUR


def check_schedule(username):
    """
    Checks if it's time to run based on schedule and blackout hours.
    
    Principles:
    - Effective: Runs when needed to complete work
    - Efficient: Skips if all users already checked
    - Conservative: Never runs during blackout hours (10PM-5AM)
    """
    r = get_redis_client()
    if not r:
        logger.warning("Redis unavailable. Defaulting to SKIP run for safety.")
        return False

    if is_in_blackout_hours():
        logger.info("Skipping run - blackout hours (10PM-5AM).")
        return False

    next_run = r.get(f"schedule:{username}:next_run")
    if next_run:
        now = datetime.now().timestamp()
        if now < float(next_run):
            wait_hours = (float(next_run) - now) / 3600
            logger.info(f"Skipping run. Next run scheduled in {wait_hours:.2f} hours.")
            return False

    return True


def update_schedule(username, all_users_checked=False):
    """
    Sets the next run time based on progress.
    
    If all users are checked:
    - Extend the wait time (reduce frequency)
    - This prevents unnecessary runs and saves resources
    """
    r = get_redis_client()
    if not r:
        return

    if all_users_checked:
        hours = random.uniform(24, 48)
        logger.info("All users already checked. Extending schedule to 24-48 hours.")
    else:
        hours = get_random_schedule_hours()

    next_run = datetime.now() + timedelta(hours=hours)
    r.set(f"schedule:{username}:next_run", next_run.timestamp())
    logger.info(f"Next run scheduled for {next_run.strftime('%Y-%m-%d %H:%M:%S')}")


def get_processed_count(username, feature_type):
    """Get count of processed users for a feature."""
    r = get_redis_client()
    if not r:
        return 0
    try:
        key = f"processed:{username}:{feature_type}"
        return r.scard(key)
    except Exception:
        return 0


def mark_user_processed(username, target_user, feature_type):
    """Marks a target user as processed for a specific feature."""
    r = get_redis_client()
    if not r:
        return False

    try:
        key = f"processed:{username}:{feature_type}"
        r.sadd(key, target_user)
        r.expire(key, PROCESSED_USER_EXPIRY_DAYS * 24 * 3600)
        return True
    except Exception as e:
        logger.error(f"Failed to mark user as processed: {e}")
        return False


def is_user_processed(username, target_user, feature_type):
    """Checks if a target user has already been processed."""
    r = get_redis_client()
    if not r:
        return False

    try:
        key = f"processed:{username}:{feature_type}"
        return r.sismember(key, target_user)
    except Exception as e:
        logger.error(f"Failed to check if user was processed: {e}")
        return False


def filter_unprocessed_users(username, user_list, feature_type):
    """Filters out users that have already been processed."""
    r = get_redis_client()
    if not r:
        logger.warning("Redis unavailable, returning unfiltered list.")
        return user_list

    try:
        key = f"processed:{username}:{feature_type}"
        unprocessed = [u for u in user_list if not r.sismember(key, u)]

        processed_count = len(user_list) - len(unprocessed)
        if processed_count > 0:
            logger.info(
                f"Filtered out {processed_count} already-processed users. "
                f"{len(unprocessed)} remaining."
            )

        return unprocessed
    except Exception as e:
        logger.error(f"Failed to filter users: {e}")
        return user_list
