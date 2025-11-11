"""
Scheduled tasks module for automatic rate updates.

This module provides cron-based scheduling for periodic Easystaff
exchange rate updates with admin notifications. Uses aiocron for
timezone-aware scheduling.
"""

import logging
import aiocron
from services.notification import NotificationService
from services.converters.easystaff_service import EasystaffService
from database.repositories import CacheRepository
from config.settings import Settings

logger = logging.getLogger(__name__)


class Scheduler:
    """
    Scheduler for automatic periodic rate updates.

    Manages cron-based scheduled tasks for fetching Easystaff exchange rates
    at configured intervals (morning, daily, afternoon). Updates cache and
    notifies admins on success or failure.

    Scheduled tasks:
    - Morning update: configured via Settings.MORNING_CRON
    - Daily update: configured via Settings.DAILY_CRON
    - Afternoon update: configured via Settings.AFTERNOON_CRON

    Attributes:
        easystaff (EasystaffService): Service for fetching Easystaff rates
        cache (CacheRepository): Repository for caching rates
        notify (NotificationService): Service for admin notifications

    Example:
        >>> scheduler = Scheduler(
        ...     easystaff_service=easystaff,
        ...     cache=cache_repo,
        ...     notification=notification_service
        ... )
        # Scheduler initialized, cron jobs registered automatically
        # Jobs will run according to configured cron expressions

    Note:
        - All schedules use timezone from Settings.SERVER_TZ
        - Cron jobs registered automatically in __init__
        - Failed updates notify admins but don't stop scheduler
        - Success notifications include new rate value
        - Uses aiocron for async cron execution
    """

    def __init__(
        self,
        easystaff_service: EasystaffService,
        cache: CacheRepository,
        notification: NotificationService
    ) -> None:
        """
        Initialize scheduler and register cron jobs.

        Creates scheduler instance with required services and immediately
        registers all periodic tasks according to cron expressions from Settings.

        Args:
            easystaff_service: Service for fetching exchange rates
            cache: Repository for caching fetched rates
            notification: Service for sending admin notifications

        Returns:
            None

        Note:
            - Cron jobs start immediately after initialization
            - Jobs run in background, don't block execution
            - Timezone configured via Settings.SERVER_TZ
        """
        self.easystaff = easystaff_service
        self.cache = cache
        self.notify = notification

        # Register all scheduled tasks
        self._init_schedules()
        logger.info("Scheduler initialized with cron jobs registered")

    def _init_schedules(self) -> None:
        """
        Register all periodic rate update tasks (internal helper).

        Creates three aiocron jobs for morning, daily, and afternoon updates
        using cron expressions from Settings. All jobs use configured timezone
        for accurate scheduling across different server locations.

        Args:
            None

        Returns:
            None

        Note:
            - Private method (prefix _) - called only from __init__
            - Jobs registered as closures capturing self reference
            - Timezone ensures consistent scheduling regardless of server TZ
            - Cron expressions format: "minute hour day month weekday"
            - Example: "0 9 * * *" = every day at 9:00 AM
        """
        # Load cron expressions from settings
        morning_cron = Settings.MORNING_CRON
        daily_cron = Settings.DAILY_CRON
        afternoon_cron = Settings.AFTERNOON_CRON

        # Use server timezone for all scheduled tasks
        tz = Settings.SERVER_TZ

        logger.info(f"Registering cron jobs with timezone: {tz}")
        logger.info(f"Morning: {morning_cron}, Daily: {daily_cron}, Afternoon: {afternoon_cron}")

        # Register morning update job
        @aiocron.crontab(morning_cron, tz=tz)
        async def morning_update():
            """Execute morning rate update."""
            await self._update_rate("Easystaff morning rate update")

        # Register daily update job
        @aiocron.crontab(daily_cron, tz=tz)
        async def daily_update():
            """Execute daily rate update."""
            await self._update_rate("Easystaff daily rate update")

        # Register afternoon update job
        @aiocron.crontab(afternoon_cron, tz=tz)
        async def afternoon_update():
            """Execute afternoon rate update."""
            await self._update_rate("Easystaff evening rate update")

    async def _update_rate(self, context: str) -> None:
        """
        Fetch and cache new exchange rate with notifications (internal helper).

        Performs complete rate update workflow: fetches rate from Easystaff,
        saves to cache, and notifies admins of success or failure. Used by
        all scheduled tasks.

        Workflow:
        1. Fetch rate from Easystaff service
        2. Validate rate is not None/zero
        3. Save rate to cache
        4. Notify admins of successful update with new rate
        5. On error: notify admins with error message

        Args:
            context: Human-readable context for notifications
                (e.g., "Easystaff morning rate update")

        Returns:
            None

        Example:
            >>> await scheduler._update_rate("Manual rate update")
            # Admins receive: "✅ Manual rate update success
            #                  New rate: 85.50 RUB/EUR"

        Note:
            - Private method (prefix _) - called only from cron jobs
            - Logs all operations at INFO level
            - Failed fetches notify admins with error details
            - Does not re-raise exceptions (scheduler continues)
            - Zero/None rates are treated as errors
        """
        logger.info(f"Starting scheduled task: {context}")

        try:
            # Fetch current rate from Easystaff
            rate = await self.easystaff.get_rate()

            # Validate rate is present and non-zero
            if rate and rate > 0:
                # Save rate to cache for bot queries
                self.cache.save(rate)
                logger.info(f"Rate updated successfully: {rate:.2f} RUB/EUR")

                # Notify admins of successful update
                await self.notify.notify_admins(
                    f"✅ {context} success\n"
                    f"New rate: {rate:.2f} RUB/EUR"
                )
            else:
                # Handle zero or None rate as error
                error_msg = f"Invalid rate received: {rate}"
                logger.error(error_msg)
                await self.notify.notify_admins(f"⛔ Error {context.lower()}: {error_msg}")

        except Exception as e:
            # Log full error with traceback
            logger.error(f"Failed to update rate for '{context}': {e}", exc_info=True)

            # Notify admins with error details (truncated for readability)
            error_text = str(e)[:200]  # Limit error message length
            await self.notify.notify_admins(
                f"⛔ Error {context.lower()}: {error_text}"
            )
