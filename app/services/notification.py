"""
Admin notification service module.

This module provides service for sending notifications to bot administrators
via Telegram messages. Handles batch sending with individual error handling.
"""

import logging
from aiogram import Bot
from typing import List
from config.settings import Settings

logger = logging.getLogger(__name__)


class NotificationService:
    """
    Service for sending notifications to bot administrators.

    Manages notification delivery to all configured admin users via Telegram.
    Handles errors gracefully for individual admins without stopping batch send.

    Attributes:
        bot (Bot): Aiogram bot instance for sending messages

    Example:
        >>> bot = Bot(token="YOUR_TOKEN")
        >>> notification = NotificationService(bot)
        >>> await notification.notify_admins("Bot started successfully")
        # All admins receive: "🛎 Bot started successfully"

    Note:
        - Admin IDs loaded from Settings.ADMIN_IDS
        - Failed sends logged but don't stop other notifications
        - Adds 🛎 emoji prefix to all admin messages
        - No retry logic (single attempt per admin)
    """

    def __init__(self, bot: Bot) -> None:
        """
        Initialize notification service with bot instance.

        Args:
            bot: Aiogram bot instance for sending Telegram messages

        Returns:
            None
        """
        self.bot = bot

    async def notify_admins(self, message: str) -> None:
        """
        Send notification message to all configured administrators.

        Iterates through all admin IDs from Settings.ADMIN_IDS and sends
        the provided message to each. Continues sending to remaining admins
        even if some sends fail. Logs errors for failed sends.

        Args:
            message: Text message to send to admins (emoji will be added automatically)

        Returns:
            None

        Raises:
            None (catches all exceptions internally)

        Example:
            >>> await notification.notify_admins("⚠️ High error rate detected")
            # Admin 123 receives: "🛎 ⚠️ High error rate detected"
            # Admin 456 receives: "🛎 ⚠️ High error rate detected"
            # If admin 789 fails: logs error and continues

        Note:
            - Automatically adds 🛎 emoji prefix to message
            - Sends to all admins in Settings.ADMIN_IDS sequentially
            - Failed sends logged at ERROR level with admin ID
            - Does not retry failed sends
            - Empty ADMIN_IDS list results in no action (logs warning)
        """
        # Check if admin list is configured
        if not Settings.ADMIN_IDS:
            logger.warning("ADMIN_IDS is empty, no notifications sent")
            return

        # Counter for tracking send results
        success_count = 0
        fail_count = 0

        # Send message to all administrators
        for admin_id in Settings.ADMIN_IDS:
            try:
                # Send notification with emoji prefix
                await self.bot.send_message(admin_id, f"🛎 {message}")
                success_count += 1
                logger.debug(f"Notification sent to admin {admin_id}")
            except Exception as e:
                # Log error but continue with other admins
                fail_count += 1
                logger.error(f"Failed to send notification to admin {admin_id}: {e}", exc_info=True)

        # Log summary of batch send
        total = len(Settings.ADMIN_IDS)
        if fail_count > 0:
            logger.warning(f"Notification batch complete: {success_count}/{total} sent, {fail_count} failed")
        else:
            logger.info(f"Notification sent to all {success_count} admins successfully")
