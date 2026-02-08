import logging
import sys
import random
import time

# Configuration limits
MIN_SLEEP = 10
MAX_SLEEP = 30

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def get_logger(name):
    return logging.getLogger(name)


def random_sleep():
    sleep_time = random.uniform(MIN_SLEEP, MAX_SLEEP)
    logger.info(f"Sleeping for {sleep_time:.2f}s...")
    time.sleep(sleep_time)
