"""
XE.com exchange rate scraping service.

Non-blocking aiohttp + BeautifulSoup parser with robust number normalization.
Returns raw EUR amount as float. Do NOT round here; presentation decides.
"""

import re
import aiohttp
import logging
from bs4 import BeautifulSoup
from typing import Optional
from config.settings import Settings

logger = logging.getLogger(__name__)

# XE.com config
XE_URL = Settings.XE_URL  # URL template with {amount}
# Prefer CSS selector that matches element having BOTH classes (p.a.b), with fallbacks
XE_RATE_CLASSES = ["sc-c5062ab2-1", "jKDFIr"]  # UI may change; fallback scan is implemented
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}


def _normalize_number(text: str) -> float:
    """
    Normalize localized number to float (no rounding).
    - Remove spaces, NBSP (U+00A0), NNBSP (U+202F) used as thousands separators.
    - Decide decimal vs thousands separators (rightmost of ,/. is decimal when both present).
    - Keep a single '.' as decimal point.
    """
    s = text.strip()
    # Keep only digits, separators, minus, and whitespace (for stripping NBSPs)
    s = re.sub(r"[^\d,.\-\s\u00A0\u202F]", "", s)
    # Remove regular spaces, NBSP and NNBSP
    s = s.replace(" ", "").replace("\u00A0", "").replace("\u202F", "")
    has_comma, has_dot = ("," in s), ("." in s)

    if has_comma and has_dot:
        # The rightmost separator is decimal; the other is thousands
        last_comma, last_dot = s.rfind(","), s.rfind(".")
        if last_dot > last_comma:
            # Dot is decimal → drop commas
            s = s.replace(",", "")
        else:
            # Comma is decimal → drop dots, then comma→dot
            s = s.replace(".", "").replace(",", ".")
    elif has_comma:
        parts = s.split(",")
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            right = parts[1]
            if len(right) == 2:
                s = parts[0] + "." + right
            elif len(right) == 3:
                s = parts[0] + right
            else:
                s = parts[0] + "." + right
        else:
            s = s.replace(",", ".")
    elif has_dot:
        parts = s.split(".")
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            right = parts[1]
            if len(right) == 3:
                s = parts[0] + right
            else:
                # keep as decimal dot
                pass

    # Strip anything but digits/dot/minus
    s = re.sub(r"[^0-9.\-]", "", s)
    # If multiple dots remain, keep the last as decimal, others as thousands
    if s.count(".") > 1:
        last = s.rfind(".")
        s = s[:last].replace(".", "") + s[last:]
    return float(s)


class XeConverterService:
    """
    Service for fetching EUR amounts from XE.com (async).

    Returns RAW EUR amount (float). Rounding/truncation is handled by caller.
    """

    @staticmethod
    async def get_rate(amount: float) -> Optional[float]:
        """
        Fetch RAW EUR amount for given RUB amount from XE.com.

        Returns:
            float: RAW EUR amount (no rounding inside).
        """
        url = XE_URL.format(amount=amount)
        try:
            # Configure per-request timeout; rely on raise_for_status to catch 4xx/5xx
            timeout = aiohttp.ClientTimeout(total=10)  # total request timeout (seconds) [aiohttp docs]
            async with aiohttp.ClientSession(timeout=timeout, headers=HEADERS) as session:
                async with session.get(url) as response:
                    response.raise_for_status()
                    html = await response.text()

            # Parse HTML
            soup = BeautifulSoup(html, "html.parser")

            # Preferred: element having BOTH classes (CSS selector combines with '.')
            result_el = soup.select_one("p." + ".".join(XE_RATE_CLASSES))  # matches all specified classes [CSS]
            if not result_el:
                # Fallback: try any one class
                result_el = (soup.find("p", class_=XE_RATE_CLASSES[0])
                             or soup.find("p", class_=XE_RATE_CLASSES[1]))
            if not result_el:
                # Fallback: scan <p> containing 'EUR' and at least one digit
                for p in soup.find_all("p"):
                    t = p.get_text(strip=True)
                    if "EUR" in t and any(ch.isdigit() for ch in t):
                        result_el = p
                        break
            if not result_el:
                raise ValueError("XE rate element not found")

            text = result_el.get_text(strip=True)
            eur_amount = _normalize_number(text)  # RAW float, no rounding
            logger.info(f"Parsed XE EUR amount: {eur_amount} for RUB={amount} from text='{text}'")
            return eur_amount

        except aiohttp.ClientError as error:
            logger.error(f"HTTP request to XE.com failed: {error}", exc_info=True)
            raise
        except Exception as error:
            logger.error(f"Failed to parse XE amount: {error}", exc_info=True)
            raise
