"""
Bot command handlers module.

This module registers and implements Telegram bot commands including
start greeting and admin statistics display with database integration.
"""

import logging
from typing import Optional
from aiogram import Dispatcher, types
from aiogram.filters import Command
from services.notification import NotificationService
from database.repositories import StatsRepository
from config.settings import Settings

logger = logging.getLogger(__name__)

# Set of admin user IDs with access to restricted commands
ADMIN_IDS = set(Settings.ADMIN_IDS or [])

"""
def _is_db_unavailable(e: Exception) -> bool:
    s = str(e).lower()
    # 1049 Unknown database, 2013 Lost connection, 2006 Gone away, общие connection ошибки
    return (
        "unknown database" in s
        or "doesn't exist" in s
        or "lost connection" in s
        or "has gone away" in s
        or "connection" in s
    )
"""


def register_commands(
    dp: Dispatcher,
    notification_service: NotificationService,
    stats_repo: Optional[StatsRepository] = None,
) -> None:
    """
    Register bot command handlers with dispatcher.

    Registers all bot commands (start, stats) as message handlers with
    appropriate filters and database integration. Handles both with-DB
    and without-DB modes gracefully.

    Args:
        dp: Aiogram dispatcher instance to register handlers with
        notification_service: Service for sending notifications (currently unused)
        stats_repo: Optional repository for user statistics tracking.
            None if database is disabled or unavailable.

    Returns:
        None

    Example:
        >>> dp = Dispatcher()
        >>> notification = NotificationService(bot)
        >>> stats_repo = StatsRepository(db) if USE_DB else None
        >>> register_commands(dp, notification, stats_repo)
        # Handlers registered and ready

    Note:
        - Handlers are registered as nested functions (closures)
        - Database operations are optional and fail gracefully
        - Admin commands check ADMIN_IDS before execution
        - All exceptions are logged but don't crash the bot
    """

    @dp.message(Command("start"))
    async def cmd_start(message: types.Message) -> None:
        """
        Handle /start command - bot greeting and usage tracking.

        Sends greeting message to user and logs their usage in database
        if database is enabled and available. Gracefully handles DB unavailability.

        Args:
            message: Incoming Telegram message with /start command

        Returns:
            None

        Note:
            - Always responds to user even if DB logging fails
            - Skips DB operations silently if USE_DB=False
            - Logs errors at ERROR level without exposing to user
            - Updates user stats on every /start invocation
        """
        # Send greeting message to user
        await message.answer("Enter the amount in rubles to convert to EUR:")

        # Skip database operations if database is disabled
        if not Settings.USE_DB:
            # The database is disabled
            return

        # Skip database operations if repository not initialized
        if stats_repo is None:
            # The database is enabled, but the repository has not been initialized - we do not interfere with the user
            return

        # Log user activity to database (best-effort, doesn't block user)
        try:
            #await stats_repo.ping()
            await stats_repo.update_user_stats(message.from_user)
        except Exception as e:
            # Log error but don't notify user - DB failure shouldn't break UX
            logger.error(f"[start] stats update failed: {e}", exc_info=True)

    @dp.message(Command("stats"))
    async def cmd_stats(message: types.Message) -> None:
        """
        Handle /stats command - display usage statistics (admin only).

        Shows comprehensive bot usage statistics including total users,
        unique users, and top 10 most active users with detailed breakdowns.
        Only accessible to users in ADMIN_IDS list.

        Args:
            message: Incoming Telegram message with /stats command

        Returns:
            None

        Note:
            - Restricted to admin users only (checked via ADMIN_IDS)
            - Returns early with error message if DB disabled/unavailable
            - Formats output as HTML table with monospace font
            - Truncates error messages to 200 chars for display
            - Displays up to 10 users ordered by total activity
        """
        # Check admin access - silently ignore non-admins
        if message.from_user.id not in ADMIN_IDS:
            return await message.answer("❌ Take a walk.")

        # Check if database is enabled in settings
        if not Settings.USE_DB:
            return await message.answer("ℹ️ The database is disabled.")

        # Check if stats repository is initialized
        if stats_repo is None:
            return await message.answer("⚠️ Database unavailable: repository not initialized.")

        # Retrieve statistics from database
        try:
            #await stats_repo.ping()
            stats = await stats_repo.get_stats()
        except Exception as e:
            # Log full error with traceback
            logger.error(f"[stats] get_stats failed: {e}", exc_info=True)
            """
            if _is_db_unavailable(e):
                return await message.answer("⚠️ The database is not accessible or not initialized.")
            """
            # Show truncated error to admin for debugging
            return await message.answer(f"⚠️ Error retrieving statistics: {str(e)[:200]}")

        # Format statistics header with summary metrics
        header = [
            "📊 <b>Bot usage statistics</b>",
            f"👥 <b>Total users:</b> {stats['total_registered_users']}",
            f"🔄 <b>Unique users:</b> {stats['total_unique_users']}",
            f"📅 <b>Current month:</b> {stats['current_month']}",
            "",
            "<b>Top 10 active users:</b>",
            "<code>",
            # Table header with column names
            "ID       | Nickname     | Name       | Total | Today   | Month |Prev.month| Last activity       ",
            "---------|--------------|------------|-------|---------|-------|----------|---------------------",
        ]

        # Format each user row as table line
        lines = []
        for u in stats["active_users"]:
            # Format username with @ prefix or dash if missing
            username = f"@{u['username']}" if u['username'] else "-"
            # Truncate first name to 10 chars for table alignment
            first_name = (u["first_name"] or "")[:10]
            # Build fixed-width table row
            lines.append(
                f"{str(u['user_id'])[:10]:<9}| "
                f"{username[:12]:<12} | "
                f"{first_name:<10} | "
                f"{u['total']:<5} | "
                f"{u['today']:<7} | "
                f"{u['month']:<5} | "
                f"{u['prev_month']:<8} | "
                f"{u['last_activity']}"
            )

        # Close code block
        footer = ["</code>"]

        # Combine all parts and send as single message
        text = "\n".join(header + lines + footer)
        await message.answer(text, parse_mode="HTML")
