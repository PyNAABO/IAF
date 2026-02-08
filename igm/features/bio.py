import time
from .base import BaseFeature


class UpdateBioFeature(BaseFeature):
    def __init__(self, bot, new_bio):
        super().__init__(bot)
        self.new_bio = new_bio

    def run(self):
        self.logger.info("Starting bio update...")
        try:
            # Go to Edit Profile page
            self.page.goto("https://www.instagram.com/accounts/edit/")
            self.sleep(3, 5)

            # Wait for the bio textarea
            # Instagram often uses a textarea with specific ID or generic tag
            # We'll try a flexible approach looking for 'Bio' label or textarea

            # 1. Try generic textarea
            bio_input = self.page.locator("textarea#pepBio")
            if not bio_input.count():
                # Fallback: look for textarea by label or placeholder if ID changes
                bio_input = self.page.locator("textarea").first

            if bio_input.count() > 0:
                self.logger.info("Bio input found. Clearing and typing new bio...")
                bio_input.click()
                bio_input.fill(self.new_bio)
                self.sleep(1, 2)

                # Look for Submit button
                # Usually type='submit' or text='Submit'
                submit_btn = self.page.locator("button[type='submit']")
                if not submit_btn.count():
                    submit_btn = self.page.get_by_role("button", name="Submit")

                if submit_btn.count() > 0:
                    submit_btn.click()
                    self.logger.info("Clicked Submit.")
                    self.sleep(3, 5)

                    # Verify functionality (optional, check for toast or reload)
                    if self.page.get_by_text("Profile saved").count() > 0:
                        self.logger.info("Bio updated successfully (Toast detected).")
                    else:
                        self.logger.info(
                            "Bio update submitted (No specific toast detected, check profile manually)."
                        )
                else:
                    self.logger.error("Submit button not found.")
            else:
                self.logger.error("Bio textarea not found.")

        except Exception as e:
            self.logger.error(f"Error updating bio: {e}")
            self.bot.screenshot("error_update_bio")
