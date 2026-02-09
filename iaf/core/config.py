import os
import re
import random
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

IG_USERNAME = os.getenv("IG_USERNAME")
REDIS_URL = os.getenv("REDIS_URL")

if not REDIS_URL:
    print(
        "WARNING: REDIS_URL is not set. Session persistence and scheduling will be disabled."
    )

if not IG_USERNAME:
    raise ValueError("IG_USERNAME must be set in .env file.")

# Timeouts (in milliseconds)
TIMEOUT_NAVIGATION = 60000
TIMEOUT_MODAL = 10000
TIMEOUT_ACTION = 5000

# Conservative Limits (Anti-Ban Priority)
PROCESSED_USER_EXPIRY_DAYS = 28
MAX_DAILY_ACTIONS = 28
MIN_DELAY_BETWEEN_ACTIONS = 30
MAX_DELAY_BETWEEN_ACTIONS = 60

# Schedule timing (for calculation only, actual timing randomized)
SCHEDULE_INTERVAL_MIN_HOURS = 3
SCHEDULE_INTERVAL_MAX_HOURS = 6

# Time blackout (no runs during these hours)
BLACKOUT_START_HOUR = 22  # 10PM
BLACKOUT_END_HOUR = 5     # 5AM

# Random schedule variance (avoid predictable patterns)
SCHEDULE_VARIANCE_DAYS = 0.3  # ±30% random variance in daily schedule

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def parse_count(text):
    """Parse Instagram count text like '1,234', '1.5M', or '691 followers' to integer."""
    if not text:
        return 0
    text = text.strip()
    text = text.replace(",", "").upper()
    
    multipliers = {"K": 1000, "M": 1000000, "B": 1000000000}
    
    match = re.match(r"([\d.]+)", text)
    if match:
        numeric_text = match.group(1)
        try:
            value = float(numeric_text)
            for suffix, mult in multipliers.items():
                if suffix in text:
                    value *= mult
                    break
            return int(value)
        except ValueError:
            return 0
    
    for suffix, mult in multipliers.items():
        if suffix in text:
            try:
                return int(float(text.replace(suffix, "")) * mult)
            except ValueError:
                return 0
    
    try:
        return int(text)
    except ValueError:
        return 0


def get_counts_from_page(page, username):
    """Extract follower and following counts from profile page."""
    try:
        page.goto(f"https://www.instagram.com/{username}/", wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
    except Exception:
        return None, None

    if page.locator("input[name='username']").count() > 0:
        print("WARNING: Session invalid - redirected to login page.")
        print("Please re-import cookies using: python -m scripts.import_cookies")
        return None, None

    followers = 0
    following = 0

    try:
        page.wait_for_selector("header", timeout=5000)
        
        header_links = page.locator("header a").all()
        for link in header_links:
            text = link.text_content() or ""
            if "followers" in text.lower() and followers == 0:
                followers = parse_count(text)
            elif "following" in text.lower() and following == 0:
                following = parse_count(text)
    except Exception as e:
        print(f"Warning: Could not extract counts from header: {e}")

    if followers == 0 or following == 0:
        try:
            header_spans = page.locator("header span").all()
            for span in header_spans:
                text = span.text_content() or ""
                if "followers" in text.lower() and followers == 0:
                    followers = parse_count(text)
                elif "following" in text.lower() and following == 0:
                    following = parse_count(text)
        except Exception:
            pass

    return followers, following


def is_in_blackout_hours():
    """Check if current time is in blackout hours (10PM-5AM)."""
    current_hour = datetime.now().hour
    if BLACKOUT_START_HOUR > BLACKOUT_END_HOUR:
        return current_hour >= BLACKOUT_START_HOUR or current_hour < BLACKOUT_END_HOUR
    return BLACKOUT_START_HOUR <= current_hour < BLACKOUT_END_HOUR


def calculate_optimal_days_to_complete(total_users, feature_type):
    """
    Calculate optimal days to complete coverage based on account size.
    
    Strategy:
    - Small accounts (<1000): Finish faster (~14-21 days)
    - Medium accounts (1000-10000): Standard 28 days
    - Large accounts (>10000): Pace to MAX_DAILY_ACTIONS
    
    This ensures efficiency while staying conservative.
    """
    if total_users <= 0:
        return PROCESSED_USER_EXPIRY_DAYS
    
    if total_users < 500:
        return max(7, int(total_users / 50))
    elif total_users < 2000:
        return max(14, int(total_users / 100))
    elif total_users < 10000:
        return PROCESSED_USER_EXPIRY_DAYS
    else:
        actions_needed = total_users / MAX_DAILY_ACTIONS
        return max(PROCESSED_USER_EXPIRY_DAYS, int(actions_needed))


def calculate_actions_per_run(follower_count, following_count, feature_type):
    """
    Calculate safe actions per run for effective, efficient, conservative coverage.
    
    Principles:
    - Effective: Completes work in reasonable time
    - Efficient: Doesn't waste actions on already-processed users
    - Conservative: Never exceeds daily limits
    """
    total_users = follower_count if feature_type == "follow" else following_count
    
    if total_users <= 0:
        return 5
    
    optimal_days = calculate_optimal_days_to_complete(total_users, feature_type)
    
    avg_hours = (SCHEDULE_INTERVAL_MIN_HOURS + SCHEDULE_INTERVAL_MAX_HOURS) / 2
    runs_per_day = 24 / avg_hours
    
    actions_needed_per_day = total_users / optimal_days
    target_daily_actions = min(actions_needed_per_day, MAX_DAILY_ACTIONS)
    
    actions_per_run = max(1, int(target_daily_actions / runs_per_day))
    safe_max = min(15, MAX_DAILY_ACTIONS // 2)
    
    return min(actions_per_run, safe_max)


def get_random_schedule_hours():
    """
    Generate random schedule hours with variance.
    Avoids running at the exact same time every day.
    """
    base_hours = random.uniform(SCHEDULE_INTERVAL_MIN_HOURS, SCHEDULE_INTERVAL_MAX_HOURS)
    variance = base_hours * SCHEDULE_VARIANCE_DAYS
    hours = base_hours + random.uniform(-variance, variance)
    return max(2, min(12, hours))  # Clamp between 2-12 hours


def should_run_today(last_run_date):
    """
    Decide if we should run today based on:
    1. Progress made (if complete, reduce frequency)
    2. Days since last run (avoid consecutive runs if not needed)
    3. Random factor (unpredictable schedule)
    """
    if not last_run_date:
        return True
    
    days_since_run = (datetime.now() - last_run_date).days
    
    if days_since_run == 0:
        return random.random() < 0.2  # 20% chance to run twice in one day
    elif days_since_run == 1:
        return random.random() < 0.5  # 50% chance
    else:
        return True  # Always run if skipped a day
