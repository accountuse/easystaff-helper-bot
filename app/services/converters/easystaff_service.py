"""
Easystaff rate scraping service using Playwright automation.

This module provides automated web scraping of EUR exchange rates
from Easystaff platform using headless Chromium browser with Playwright.
Handles authentication, navigation, and rate extraction with optional tracing.
"""

import logging
from pathlib import Path
from playwright.async_api import async_playwright, Page, Locator
from config.settings import Settings

logger = logging.getLogger(__name__)

# Easystaff configuration
EASYSTAFF_URL = Settings.EASYSTAFF_URL
TRACING_ENABLED = Settings.TRACING_ENABLED

# Easystaff CSS selectors for automated navigation
EMAIL_INPUT_SELECTOR = 'input[type="email"]'
PASSWORD_INPUT_SELECTOR = 'input[type="password"]'
LOGIN_BUTTON_SELECTOR = 'button:has-text("Log in")'
AFTER_LOGIN_GROUP_SELECTOR = '.bubble-element.Group.baTiaYaA0.bubble-r-container'
IMAGE_BUTTON_SELECTOR = '.bubble-element.Group.baTiaYaA0.bubble-r-container .clickable-element.bubble-element.Image.baTiaXi0'
SECOND_GROUP_SELECTOR = '.bubble-element.Group.baTiaXo0.bubble-r-container'
SECOND_BUTTON_SELECTOR = '.clickable-element.bubble-element.Group.baTvaIaQ0'
CURRENCY_LIST_SELECTOR = '.bubble-element.Group.baTlaSd0.bubble-r-container'
EUR_ITEM_SELECTOR = '.bubble-element.Group.baTlaSd0.bubble-r-container .bubble-element.Text.baTlaSe0'
EUR_VALUE_SELECTOR = '.bubble-element.Text.baTlaSaG0.bubble-r-vertical-center'


def _parse_rate_text(text: str) -> float:
    """
    Parse rate text to float safely (no rounding).

    - Remove regular spaces, NBSP U+00A0 and NNBSP U+202F used as thousands separators. [web:411]
    - Replace comma with dot as decimal separator.
    - Strip non-digit/decimal characters before float().

    Example inputs:
      "89,25" -> 89.25
      "89 25" (U+202F) -> 89.25
      "89.25 RUB/EUR" -> 89.25
    """
    # Remove spaces and narrow/no-break spaces used as thousands separators
    s = (text or "").strip().replace(" ", "").replace("\u00A0", "").replace("\u202F", "")  # [web:411]
    # Use '.' as decimal separator
    s = s.replace(",", ".")
    # Keep digits, dot and optional leading minus
    filtered = []
    for ch in s:
        if ch.isdigit() or ch == "." or (ch == "-" and not filtered):
            filtered.append(ch)
    num = "".join(filtered)
    return float(num)


class EasystaffService:
    """
    Service for scraping EUR exchange rate from Easystaff platform.

    Automates browser interaction with Easystaff web interface using
    Playwright to log in, navigate currency selection, and extract
    current EUR/RUB exchange rate. Supports tracing for debugging.
    """

    def __init__(
        self,
        email: str = Settings.EASYSTAFF_EMAIL,
        password: str = Settings.EASYSTAFF_PASSWORD
    ) -> None:
        """
        Initialize Easystaff service with credentials.

        Args:
            email: Easystaff account email (default from Settings)
            password: Easystaff account password (default from Settings)
        """
        self.email = email
        self.password = password
        self._session = None  # Reserved for future session management

    async def _require_editable_locator(
        self,
        page: Page,
        selector: str,
        timeout: int = 20_000,
        name: str | None = None
    ) -> Locator:
        """
        Wait for element to be visible and editable (internal helper).

        Playwright auto-waits for editability on fill/clear, but explicit
        checks here reduce flakiness on slow UIs before interacting. [web:473]
        """
        try:
            loc = page.locator(selector).first
            await loc.wait_for(state="visible", timeout=timeout)
            eh = await loc.element_handle()
            if not eh:
                raise Exception(f'Element "{name or selector}" found but element_handle is None')
            await eh.wait_for_element_state("editable", timeout=timeout)  # explicit editable check [web:469]
            return loc
        except Exception as ex:
            logger.error(f'Editable element not found or not ready: "{name or selector}". Details: {ex}')
            raise TimeoutError(f'Editable element not found or not ready: "{name or selector}". Details: {ex}')

    async def _require_locator(
        self,
        page: Page,
        selector: str,
        timeout: int = 20_000,
        name: str | None = None
    ) -> Locator:
        """
        Wait for element to be visible (internal helper).

        Plain visibility wait for non-input elements; actions still benefit
        from Playwright’s auto-wait/actionability checks. [web:473]
        """
        try:
            loc = page.locator(selector).first
            await loc.wait_for(state="visible", timeout=timeout)
            return loc
        except Exception as ex:
            logger.error(f'Element not found: "{name or selector}". Details: {ex}')
            raise TimeoutError(f'Element not found: "{name or selector}". Details: {ex}')

    async def get_rate(self) -> float:
        """
        Scrape current EUR/RUB exchange rate from Easystaff platform (RAW float).

        Workflow:
          1) Launch headless Chromium
          2) Navigate and log in
          3) Open currency section and pick EUR
          4) Read rate text and parse to RAW float (no rounding)
          5) Close resources; return rate

        Notes:
          - context.tracing.start/stop used if TRACING_ENABLED, per docs. [web:476][web:479]
          - Playwright auto-waits for visibility/editability on actions (click/fill). [web:473]
        """
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
            )
            context = await browser.new_context()

            if TRACING_ENABLED:
                logger.info("Tracing enabled, starting tracing.")
                await context.tracing.start(screenshots=True, snapshots=True, sources=True)  # [web:476]

            page = await context.new_page()
            page.set_default_timeout(40_000)

            #artifacts_dir = Path("/app/storage/artifacts")
            #artifacts_dir.mkdir(parents=True, exist_ok=True)
            artifacts_dir = Settings.ARTIFACTS_DIR

            try:
                # Login flow
                logger.info(f'Navigating to {EASYSTAFF_URL}')
                await page.goto(EASYSTAFF_URL, wait_until="domcontentloaded", timeout=120_000)

                email = await self._require_editable_locator(page, EMAIL_INPUT_SELECTOR, name="Email input")
                await email.click()
                await email.fill(self.email, timeout=20_000)

                pwd = await self._require_editable_locator(page, PASSWORD_INPUT_SELECTOR, name="Password input")
                try:
                    await pwd.fill(self.password, timeout=20_000)
                except Exception:
                    logger.warning("Password fill failed, trying force click.")
                    await pwd.click(force=True)
                    await pwd.fill(self.password, timeout=20_000)

                login_btn = await self._require_locator(page, LOGIN_BUTTON_SELECTOR, name="Log in Button")
                await login_btn.click()

                await self._require_locator(page, AFTER_LOGIN_GROUP_SELECTOR, name="After-login group")

                img_btn = await self._require_locator(page, IMAGE_BUTTON_SELECTOR, name="Image Button")
                await img_btn.click()
                await img_btn.click()  # second click opens the menu reliably

                await self._require_locator(page, SECOND_GROUP_SELECTOR, name="Second Group")

                button2 = await self._require_locator(page, SECOND_BUTTON_SELECTOR, name="Second Button")
                await button2.click()

                await self._require_locator(page, CURRENCY_LIST_SELECTOR, name="Currency List")

                eur_item = await self._require_locator(page, EUR_ITEM_SELECTOR, name="EUR Item")
                await eur_item.click()

                result_elem = await self._require_locator(page, EUR_VALUE_SELECTOR, name="EUR Value")
                eur_text = await result_elem.inner_text()

                # On success, stop trace
                if TRACING_ENABLED:
                    await context.tracing.stop(path=str(artifacts_dir / "trace.zip"))  # [web:476]
                    logger.info(f"Tracing saved to {artifacts_dir / 'trace.zip'}")

            except Exception as exc:
                logger.error(f"Exception occurred: {exc}")
                if TRACING_ENABLED:
                    try:
                        await context.tracing.stop(path=str(artifacts_dir / "trace_failed.zip"))  # [web:476]
                        logger.info(f"Tracing (failed) saved to {artifacts_dir / 'trace_failed.zip'}")
                    except Exception:
                        logger.error("Failed to stop tracing after exception.")
                await context.close()
                await browser.close()
                raise RuntimeError(f"ERROR occurred: {exc}")
            finally:
                try:
                    await context.close()
                finally:
                    await browser.close()

            # Parse extracted text to RAW float without rounding
            return _parse_rate_text(eur_text)  # safe normalization for U+202F and commas [web:411]
