"""
Message handlers for currency conversion.

Works with RAW values for calculations and truncates to 2 decimals
for user-facing display without rounding (presentation-only). This
separates calculation accuracy from display policy.
"""

import logging
from math import ceil
from decimal import Decimal, ROUND_HALF_UP
from aiogram import types, Bot, Dispatcher
from services.converters import XeConverterService, EasystaffService
from database.repositories import CacheRepository, StatsRepository
from services.notification import NotificationService
from utils import format_datetime, trunc2
from handlers.error_handler import handle_error

logger = logging.getLogger(__name__)


class MessageHandler:
    """
    Process free-text messages as RUB amounts and reply with EUR conversions.

    Policy:
    - Services return RAW values:
        * XeConverterService.get_rate(rub) -> RAW EUR float (no rounding)
        * EasystaffService.get_rate() -> RAW RUB/EUR rate (float, no rounding)
    - Compute difference and choose recommendation on RAW values for accuracy.
    - Present values by truncating to 2 decimals (no rounding), so users decide rounding.
    - Additionally show an invoicing hint: integer rounded up (ceil) for “Rounded to use”.
    """

    def __init__(
        self,
        xe_service: XeConverterService,
        easystaff_service: EasystaffService,
        cache_repo: CacheRepository,
        stats_repo: StatsRepository | None,
        notification: NotificationService
    ) -> None:
        """
        Initialize message handler with required services and repositories.

        Args:
            xe_service: Service providing RAW EUR result from XE for a RUB amount.
            easystaff_service: Service providing RAW RUB/EUR rate from Easystaff.
            cache_repo: Repository for caching Easystaff rate and timestamp.
            stats_repo: Optional repository for user statistics tracking (can be None).
            notification: Service to send admin notifications on errors.
        """
        self.xe = xe_service
        self.easystaff = easystaff_service
        self.cache = cache_repo
        self.stats = stats_repo
        self.notify = notification

    async def _update_user_stats(self, message: types.Message) -> None:
        """
        Best-effort stats update; never blocks or breaks user flow.

        Notes:
            - Skips silently if stats_repo is not configured.
            - Logs errors and notifies admins via central error handler.
        """
        if self.stats is None:
            logger.warning("StatsRepository not initialized, skipping stats update.")
            return
        try:
            await self.stats.update_user_stats(message.from_user)
        except Exception as e:
            logger.error(f"Error updating user stats: {e}", exc_info=True)
            await handle_error(message, e, self.notify.bot, "when updating statistics")

    async def handle_conversion(self, message: types.Message, bot: Bot) -> None:
        """
        Convert a user-provided RUB amount to EUR using two sources (XE/Easystaff).

        Steps:
            1) Validate input as positive RUB amount (min 10,000 RUB).
            2) Fetch RAW EUR from XE (no rounding inside the service).
            3) Obtain RAW RUB/EUR rate from Easystaff (from cache or fetch/save).
            4) Compute RAW EUR for Easystaff result: EUR = RUB / rate.
            5) Compute percentage difference and choose recommended RAW value.
            6) Present both values truncated to 2 decimals (no rounding).
            7) Additionally, present “Rounded to use” = ceil(recommended RAW).
        """
        # 1) Update stats in the background (never blocks)
        await self._update_user_stats(message)

        # 2) Validate input
        try:
            rub_amount = float(message.text)
            if rub_amount <= 0:
                return await message.reply("❌ The amount must be a positive number greater than zero.")
            if rub_amount < 10000:
                return await message.reply("ℹ️ The minimum amount for conversion is 10,000 RUB.")
        except ValueError:
            return await message.reply("⚠️ Please use only the number")

        try:
            # 3) RAW EUR from XE (service does not round/truncate)
            eur_xe_raw = await self.xe.get_rate(rub_amount)

            # 4) Easystaff rate: from cache or fetch/save if missing
            #cache = self.cache.load()
            #if not cache or "rate" not in cache:
            #    await message.reply("⏳ Receiving the Easystaff rate, please wait.")
            #    easy_rate = await self.easystaff.get_rate()
            #    self.cache.save(easy_rate)
            #    cache = self.cache.load()

            #easy_rate = cache.get("rate")

            cache = self.cache.load() or {}
            easy_rate = cache.get("rate")

            if easy_rate is None:
                await message.reply("⏳ Receiving the Easystaff rate, please wait.")
                easy_rate = await self.easystaff.get_rate()

                if easy_rate is None:
                    return await message.reply("⚠️ Failed to get the Easystaff rate. Try again later.")

                self.cache.save(easy_rate)
                cache = self.cache.load() or {}

            # RAW EUR for Easystaff path (no rounding): RUB / (RUB/EUR) = EUR
            eur_easy_raw = (rub_amount / easy_rate) if easy_rate else 0.0

            # Validate both RAW values
            if not eur_xe_raw or eur_xe_raw <= 0 or not eur_easy_raw or eur_easy_raw <= 0:
                return await message.reply("⚠️ Received a zero/invalid rate. Try again later.")

            # 5) Compute difference and recommendation on RAW values (accuracy first)
            diff = abs(eur_xe_raw - eur_easy_raw)
            percent_diff = diff / min(eur_xe_raw, eur_easy_raw) * 100
            used_value_raw = max(eur_xe_raw, eur_easy_raw) if percent_diff <= 10 else min(eur_xe_raw, eur_easy_raw)

            # 6) Presentation-only: truncate to 2 decimals (no rounding)
            eur_xe_show = trunc2(eur_xe_raw)
            eur_easy_show = trunc2(eur_easy_raw)
            used_value_show = trunc2(used_value_raw)

            # 7) Invoicing hint: integer rounded up from the RAW recommended value
            #rounded_to_use = int(ceil(used_value_raw))

            rounded_to_use = int(
                Decimal(str(used_value_raw)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            )

            # Format Easystaff timestamp for display
            updated_time = format_datetime(cache.get("updated_at"))

            # Final user reply
            await message.reply(
                f"Amount at the XE rate: {eur_xe_show:.2f} EUR\n"
                f"Amount at the Easystaff rate: {eur_easy_show:.2f} EUR\n"
                f"The difference between them: {percent_diff:.2f}%\n\n"
                f"Recommended to use: {used_value_show:.2f} EUR\n"
                f"Rounded to use: {rounded_to_use} EUR\n\n"
                f"📅 Easystaff rate: {easy_rate} RUB/EUR \n"
                f"(updated on: {updated_time})"
            )

        except Exception as error:
            # Centralized error reporting + admin notification
            logger.error(f"Error during conversion handling: {error}", exc_info=True)
            await handle_error(message, error, self.notify.bot, context="")

    def register(self, dp: Dispatcher) -> None:
        """
        Register text message handler for non-command updates.

        Notes:
            - Keep registration last so command filters take precedence.
        """
        dp.message.register(self.handle_conversion)
