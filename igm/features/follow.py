import time
import random
from .base import BaseFeature
from igm.core.config import TIMEOUT_MODAL, MAX_ACTIONS_PER_RUN

from igm.core.config import TIMEOUT_MODAL, MAX_ACTIONS_PER_RUN


class FollowFeature(BaseFeature):
    def run(self):
        """Follows users back (Fans)."""
        self.logger.info("Checking 'Followers' list for fans...")
        username = self.bot.username

        self.page.goto(
            f"https://www.instagram.com/{username}/", wait_until="domcontentloaded"
        )
        time.sleep(3)

        try:
            self.page.locator(f"a[href='/{username}/followers/']").click()
            self.page.wait_for_selector("div[role='dialog']", timeout=TIMEOUT_MODAL)
        except Exception as e:
            self.logger.warning(f"Could not open 'Followers' dialog: {e}")
            return

        time.sleep(3)

        links = self.page.locator("div[role='dialog'] a[role='link'][href^='/']").all()
        if not links:
            links = self.page.locator("div[role='dialog'] a[href^='/']").all()

        usernames = []
        for link in links:
            href = link.get_attribute("href")
            if href and href.count("/") == 2:
                user = href.strip("/")
                if user != username:
                    usernames.append(user)

        all_usernames = list(set(usernames))
        targets = all_usernames[:MAX_ACTIONS_PER_RUN]

        self.logger.info(f"Found {len(targets)} fans to check.")

        count = 0
        for user in targets:
            if count >= MAX_ACTIONS_PER_RUN:
                break

            self.logger.info(f"Checking {user}...")
            try:
                if self.process_single_user(user):
                    count += 1
            except Exception as e:
                self.logger.error(f"Error checking {user}: {e}")

        self.logger.info(f"Followed back {count} users.")

    def process_single_user(self, user):
        self.page.goto(
            f"https://www.instagram.com/{user}/", wait_until="domcontentloaded"
        )
        self.sleep(3, 6)

        # 1. Check if WE already follow THEM
        if (
            self.page.locator("button").filter(has_text="Following").count() > 0
            or self.page.locator("button").filter(has_text="Requested").count() > 0
        ):
            self.logger.info(f"Already following {user}. Skipping.")
            return False

        # 2. Check for "Follow Back" button
        if self.page.locator("button").filter(has_text="Follow Back").count() > 0:
            self.logger.info(f"Found 'Follow Back' button for {user}. Following...")
            self.page.locator("button").filter(has_text="Follow Back").first.click()
            self.sleep()
            return True

        # 3. Check for "Follows you" badge
        if self.page.get_by_text("Follows you").count() > 0:
            self.logger.info(f"{user} follows you (badge detected). Following back...")
            follow_btn = self.page.locator("button").filter(has_text="Follow").first
            if follow_btn.count() > 0:
                follow_btn.click()
                self.sleep()
                return True

        self.logger.info(
            f"{user} found in followers list but no indicator on profile. Skipping."
        )
        return False
