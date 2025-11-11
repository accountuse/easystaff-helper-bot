"""
Bot main entry point with initialization and lifecycle management.

This module provides the main bot initialization, service setup,
database connection, and graceful shutdown handling. Coordinates
all bot components and manages the complete lifecycle.
"""

import asyncio
import logging
import signal
from aiogram import Bot, Dispatcher
from config.settings import Settings
from database.repositories import CacheRepository, StatsRepository
from services import NotificationService, XeConverterService, EasystaffService
from handlers import register_commands, MessageHandler
from services import Scheduler
from core.logger import setup_logger
from database.connection_async import AsyncDatabaseConnection

setup_logger()
logger = logging.getLogger(__name__)

# Global event for graceful shutdown signaling
shutdown_event = asyncio.Event()


def handle_shutdown_signal(signum, frame):
    """
    Signal handler for SIGTERM and SIGINT.

    Handles system shutdown signals (docker stop, system reboot, Ctrl+C)
    by setting shutdown event to trigger graceful bot termination.

    Args:
        signum: Signal number received
        frame: Current stack frame (unused)

    Returns:
        None

    Note:
        - Registered for SIGTERM (docker stop) and SIGINT (Ctrl+C)
        - Sets global shutdown_event to trigger graceful shutdown
        - Allows bot to send "stopped" notification before exit
    """
    logger.info(f"Received signal {signum}, initiating graceful shutdown...")
    shutdown_event.set()


async def connect_with_retries(
    make_conn,
    retries: int = 6,
    base: float = 0.5,
    cap: float = 5.0
):
    """
    Connect to database with exponential backoff retry logic.

    Attempts database connection multiple times with increasing delays
    between retries. Uses exponential backoff with jitter to handle
    temporary network issues or database startup delays.

    Retry delay formula:
    delay = min(cap, base * 2^(attempt-1)) * random(1.0, 1.4)

    Args:
        make_conn: Async callable that creates and returns connection
        retries: Maximum number of connection attempts (default: 6)
        base: Base delay in seconds for backoff calculation (default: 0.5)
        cap: Maximum delay cap in seconds (default: 5.0)

    Returns:
        Connected AsyncDatabaseConnection instance

    Raises:
        Exception: Re-raises last connection error if all retries exhausted

    Example:
        >>> async def make_conn():
        ...     conn = AsyncDatabaseConnection(...)
        ...     await conn.connect()
        ...     return conn
        >>> db = await connect_with_retries(make_conn, retries=3)
        # Attempts connection up to 3 times with exponential backoff

    Note:
        - Delay increases exponentially: 0.5s, 1s, 2s, 4s, 5s (cap), 5s
        - Jitter (1.0-1.4 multiplier) prevents thundering herd
        - Useful for Docker compose where DB may start after bot
        - Logs warning for each failed attempt with retry delay
    """
    import random

    # Attempt connection with exponential backoff
    for attempt in range(1, retries + 1):
        try:
            # Try to establish connection
            return await make_conn()
        except Exception as e:
            # If this was last attempt, re-raise exception
            if attempt == retries:
                raise

            # Calculate delay with exponential backoff and jitter
            delay = min(cap, base * (2 ** (attempt - 1))) * random.uniform(1.0, 1.4)
            logger.warning(f"DB connect attempt {attempt}/{retries} failed: {e}; retry in {delay:.1f}s")

            # Wait before next retry
            await asyncio.sleep(delay)


async def main() -> None:
    """
    Main bot initialization and execution function.

    Initializes all bot services, connects to database (if enabled),
    registers handlers, starts scheduler, and runs bot polling with
    graceful shutdown support.

    Initialization steps:
    1. Create bot and dispatcher instances
    2. Initialize core services (notification, converters, cache)
    3. Connect to database (optional, with retries)
    4. Register command and message handlers
    5. Start scheduler for periodic rate updates
    6. Send startup notification to admins
    7. Start polling with graceful shutdown handling
    8. Send shutdown notification and cleanup resources

    Args:
        None

    Returns:
        None

    Raises:
        None (catches all exceptions for graceful handling)

    Note:
        - Registers SIGTERM/SIGINT handlers for graceful shutdown
        - Database connection optional (controlled by Settings.USE_DB)
        - Continues in degraded mode if DB connection fails
        - Always sends shutdown notification before exit
        - Properly closes all resources in finally block
        - Polling can be interrupted by shutdown_event
    """
    logger.info("Starting bot")

    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, handle_shutdown_signal)  # Docker stop / system shutdown
    signal.signal(signal.SIGINT, handle_shutdown_signal)   # Ctrl+C

    # Initialize bot and dispatcher
    bot = Bot(token=Settings.API_TOKEN)
    dp = Dispatcher()

    # Initialize core services
    notification = NotificationService(bot)
    xe_service = XeConverterService()
    easystaff_service = EasystaffService()
    cache_repo = CacheRepository()

    # Database connection and stats repository (optional)
    stats_repo = None
    db_conn = None

    # Connect to database if enabled in settings
    if Settings.USE_DB:
        # Define connection factory for retry logic
        async def make_conn():
            conn = AsyncDatabaseConnection(
                host=Settings.DB_HOST,
                user=Settings.DB_USER,
                password=Settings.DB_PASSWORD,
                database=Settings.DB_NAME,
                port=int(Settings.DB_PORT),
            )
            await conn.connect()
            return conn

        # Attempt connection with exponential backoff
        try:
            db_conn = await connect_with_retries(make_conn)
            stats_repo = StatsRepository(db_conn)
            logger.info("Connected to database, StatsRepository initialized")
        except Exception as e:
            logger.error(f"Failed to connect DB/initialize StatsRepository: {e}", exc_info=True)
            # Continue without the database (degraded mode)
            stats_repo = None
            logger.warning("Running in degraded mode without database")
    else:
        logger.info("Database disabled (USE_DB=False)")

    # Register command handlers (/start, /stats)
    register_commands(dp, notification, stats_repo)

    # Register message handlers (currency conversion)
    msg_handlers = MessageHandler(
        xe_service=xe_service,
        easystaff_service=easystaff_service,
        cache_repo=cache_repo,
        stats_repo=stats_repo,
        notification=notification
    )
    msg_handlers.register(dp)

    # Initialize scheduler for periodic rate updates
    scheduler = Scheduler(
        easystaff_service=easystaff_service,
        cache=cache_repo,
        notification=notification
    )

    try:
        # Notify admins about successful bot startup
        await notification.notify_admins("🤖 Bot has been launched")

        # Create polling task
        polling_task = asyncio.create_task(dp.start_polling(bot))

        # Create shutdown watcher task
        shutdown_task = asyncio.create_task(shutdown_event.wait())

        # Wait for either polling to finish or shutdown signal
        done, pending = await asyncio.wait(
            [polling_task, shutdown_task],
            return_when=asyncio.FIRST_COMPLETED
        )

        # If shutdown signal received, cancel polling gracefully
        if shutdown_event.is_set():
            logger.info("Shutdown signal detected, stopping polling...")
            polling_task.cancel()
            try:
                await polling_task
            except asyncio.CancelledError:
                logger.info("Polling cancelled successfully")

    except Exception as e:
        logger.exception(f"Critical error in main loop: {e}")
    finally:
        # Send shutdown notification before closing resources
        try:
            await notification.notify_admins("🛑 Bot has been stopped")
        except Exception as e:
            logger.error(f"Failed to send shutdown notification: {e}")

        # Cleanup: close bot session
        await bot.session.close()

        # Cleanup: close database connection if exists
        if db_conn:
            try:
                await db_conn.close()
                logger.info("Database connection closed")
            except Exception:
                logger.exception("Error while closing DB connection")

        logger.info("Bot shutdown complete")


if __name__ == '__main__':
    """
    Script entry point.

    Runs main async function using asyncio.run() which handles
    event loop creation, execution, and cleanup automatically.
    """
    asyncio.run(main())
