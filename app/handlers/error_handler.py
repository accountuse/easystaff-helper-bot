"""
Error handling module for bot operations.

This module provides centralized error handling with user notifications,
admin alerts, and detailed error logging with unique error IDs.
"""

import logging
from asyncio import sleep
from aiogram import types
from aiogram import Bot
from config.settings import Settings

logger = logging.getLogger(__name__)


async def handle_error(
    message: types.Message,
    error: Exception,
    bot: Bot,
    context: str = ""
) -> None:
    """
    Handle bot errors with logging, admin notification, and user feedback.

    Generates unique error ID, logs error with full traceback, notifies
    first admin in ADMIN_IDS list, and sends friendly error message to user.
    Used as centralized error handler for all bot operations.

    Args:
        message: Telegram message that triggered the error
        error: Exception instance that was raised
        bot: Bot instance for sending notifications
        context: Optional context description (e.g., "in currency conversion")
            to help identify error source

    Returns:
        None

    Example:
        >>> try:
        ...     await process_currency_conversion(message)
        ... except Exception as e:
        ...     await handle_error(message, e, bot, "in currency conversion")
        # Logs error, notifies admin, replies to user

    Note:
        - Error ID is 6-digit hash for easy reference in logs
        - Only first admin from ADMIN_IDS receives notification
        - User receives friendly message with error ID for support
        - Full traceback logged at ERROR level for debugging
        - Does not re-raise exception - assumes error is handled
    """
    # Generate unique 6-digit error ID from exception hash for tracking
    error_id = f"ERR-{hash(error) % 1000000}"

    # Format error header with context and metadata
    error_header = (
        f"[{error_id}] Ошибка {context}\n"
        f"User: {message.from_user.id} | Chat: {message.chat.id}\n"
        f"Message: '{message.text}'\n"
        f"Error: {type(error).__name__}"
    )

    # Log full error with traceback for debugging
    logger.error(
        f"{error_header}\n"
        f"Details: {str(error)}",
        exc_info=True  # Include full traceback in logs
    )

    # Send notification to first admin if admins are configured
    if Settings.ADMIN_IDS:
        text = (
            f"⚠️ Error {error_id}\n"
            f"User: {message.from_user.id}\n"
            f"Type: {type(error).__name__}\n"
            f"Text: {str(error)}\n"
            f"Context: {context or 'n/a'}"
        )
        for i, admin_id in enumerate(Settings.ADMIN_IDS):
            try:
                await bot.send_message(admin_id, text)
            except Exception as e:
                logger.error(f"Failed to notify admin {admin_id}: {e}")
            # Soft pacing to respect API flood limits
            if i + 1 < len(Settings.ADMIN_IDS):
                await sleep(0.05)  # ~20 msgs/sec overall

    # Send friendly error message to user with error ID for reference
    #await message.answer(
    await message.reply(  # Use reply to quote user's message
        "😕 An error occurred."
        f"Error ID: {error_id}\n"
        "The administrator has already been notified. Please try again later."
    )
