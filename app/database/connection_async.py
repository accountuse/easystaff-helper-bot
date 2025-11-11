"""
Async database connection module with auto-reconnect support.

This module provides asynchronous MySQL/MariaDB connection management
with automatic reconnection on connection loss, using asyncmy driver.
"""

import asyncmy
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

logger = logging.getLogger(__name__)


class AsyncDatabaseConnection:
    """
    Async MySQL/MariaDB connection wrapper with automatic reconnection.

    Manages database connection lifecycle with built-in health checks
    and transparent reconnection on connection loss (timeouts, network issues,
    server restarts). Uses asyncmy driver for async operations.

    Attributes:
        config (dict): Database connection configuration dictionary
        conn (asyncmy.Connection | None): Active connection instance or None

    Example:
        >>> db = AsyncDatabaseConnection(
        ...     host="localhost",
        ...     user="app_user",
        ...     password="secret",
        ...     database="mydb"
        ... )
        >>> await db.connect()
        >>> async with db.get_cursor() as cur:
        ...     await cur.execute("SELECT * FROM users")
        ...     rows = await cur.fetchall()
        >>> await db.close()

    Note:
        - All database operations should use get_cursor() context manager
          for automatic reconnection support
        - Connection uses autocommit mode by default
        - Ping-based health checks before each query prevent stale connections
    """

    def __init__(
        self,
        *,
        host: str,
        user: str,
        password: str,
        database: str,
        port: int = 3306
    ) -> None:
        """
        Initialize database connection configuration.

        Creates connection config dictionary but does not establish
        connection yet. Call connect() explicitly to connect.

        Args:
            host: Database server hostname or IP address
            user: Database username for authentication
            password: Database password for authentication
            database: Database name to connect to
            port: Database server port (default: 3306)

        Returns:
            None

        Note:
            - Uses keyword-only arguments for clarity and safety
            - Autocommit is enabled by default (no manual commit needed)
            - Connection timeout set to 10 seconds
        """
        self.config = {
            "host": host,
            "user": user,
            "password": password,
            "db": database,
            "port": port,
            "autocommit": True,
            "connect_timeout": 10,
        }
        self.conn = None

    async def connect(self) -> None:
        """
        Establish new connection to database server.

        Closes existing connection (if any) and creates fresh connection
        using configured credentials. Logs successful connection.

        Args:
            None

        Returns:
            None

        Raises:
            asyncmy.errors.Error: On connection failure (auth, network, etc.)

        Example:
            >>> db = AsyncDatabaseConnection(host="localhost", ...)
            >>> await db.connect()
            # INFO: Connected to database: mydb@localhost

        Note:
            - Automatically closes stale connection before reconnecting
            - Connection errors are not caught - caller should handle
            - Logs connection details at INFO level
        """
        # Close existing connection gracefully before creating new one
        if self.conn is not None:
            try:
                await self.conn.ensure_closed()
            except Exception:
                pass  # Ignore errors on closing stale connection

        # Establish new connection with configured parameters
        self.conn = await asyncmy.connect(**self.config)
        logger.info(f"Connected to database: {self.config['db']}@{self.config['host']}")

    async def ensure_connected(self) -> None:
        """
        Ensure database connection is alive and healthy.

        Performs connection health check via ping and automatically
        reconnects if connection is dead, timed out, or non-existent.
        Should be called before every database operation.

        Args:
            None

        Returns:
            None

        Raises:
            asyncmy.errors.Error: If reconnection fails after ping failure

        Example:
            >>> await db.ensure_connected()
            # DEBUG: Connection ping successful
            # or
            # WARNING: Connection lost (ping failed): ... Reconnecting...

        Note:
            - Uses asyncmy's ping(reconnect=True) for efficient health check
            - Handles OperationalError (timeout) and InterfaceError (closed conn)
            - Logs at WARNING/ERROR for connection issues, DEBUG for success
            - Called automatically by get_cursor() - manual call rarely needed
        """
        # If no connection exists, create new one
        if self.conn is None:
            logger.warning("No connection exists, creating new one...")
            await self.connect()
            return

        # Try to ping existing connection to verify it's alive
        try:
            # asyncmy supports ping with auto-reconnect flag
            await self.conn.ping(reconnect=True)
            logger.debug("Connection ping successful")
        except (asyncmy.errors.OperationalError, asyncmy.errors.InterfaceError) as e:
            # Connection lost or timed out - reconnect
            logger.warning(f"Connection lost (ping failed): {e}. Reconnecting...")
            await self.connect()
        except Exception as e:
            # Unexpected error during ping - try to reconnect anyway
            logger.error(f"Unexpected error during ping: {e}. Attempting reconnect...")
            await self.connect()

    def cursor(self):
        """
        Get database cursor from active connection.

        Returns cursor object for executing queries. Note that cursor()
        itself is NOT awaitable, but cursor operations (execute, fetch) are.

        Args:
            None

        Returns:
            asyncmy.Cursor: Database cursor for query execution

        Raises:
            RuntimeError: If called when connection is not established

        Example:
            >>> cur = db.cursor()
            >>> await cur.execute("SELECT 1")
            >>> result = await cur.fetchone()
            >>> await cur.close()

        Note:
            - cursor() is NOT async, but cursor methods (execute, fetch) are
            - Direct use discouraged - prefer get_cursor() context manager
            - Cursor must be closed manually if not using context manager
            - Does NOT perform connection health check - use ensure_connected()
        """
        if self.conn is None:
            raise RuntimeError("Connection is not established. Call connect() first.")
        return self.conn.cursor()

    @asynccontextmanager
    async def get_cursor(self) -> AsyncGenerator:
        """
        Async context manager for database cursor with auto-reconnect.

        Yields cursor for database operations, ensuring connection is alive
        before use and properly closing cursor afterwards. Automatically
        handles connection loss and reconnection.

        Args:
            None

        Yields:
            asyncmy.Cursor: Active database cursor for queries

        Raises:
            asyncmy.errors.OperationalError: On connection errors during query
            asyncmy.errors.InterfaceError: On connection interface errors
            Exception: Other database errors during query execution

        Example:
            >>> async with db.get_cursor() as cur:
            ...     await cur.execute("INSERT INTO users VALUES (%s)", (123,))
            ...     # Cursor automatically closed after block

        Note:
            - PREFERRED method for all database operations
            - Ensures connection health before yielding cursor
            - Automatically closes cursor in finally block
            - Logs connection errors at ERROR level
            - Re-raises exceptions after logging for caller handling
        """
        # Ensure connection is alive before creating cursor
        await self.ensure_connected()

        # Get cursor from active connection
        cur = self.cursor()
        try:
            yield cur
        except (asyncmy.errors.OperationalError, asyncmy.errors.InterfaceError) as e:
            # If query fails due to connection error, log and re-raise
            logger.error(f"Database operation failed (connection error): {e}")
            raise
        except Exception as e:
            # Other database errors (syntax, constraint violations, etc.)
            logger.error(f"Database operation failed: {e}")
            raise
        finally:
            # Always close cursor, even if exception occurred
            await cur.close()

    async def close(self) -> None:
        """
        Close database connection and release resources.

        Gracefully closes active connection and sets conn to None.
        Safe to call multiple times or when connection is already closed.

        Args:
            None

        Returns:
            None

        Raises:
            None (catches and logs all exceptions)

        Example:
            >>> await db.close()
            # INFO: Database connection closed

        Note:
            - Safe to call even if connection is None or already closed
            - Logs success at INFO level, errors at ERROR level
            - Sets self.conn to None in finally block for clean state
            - Should be called in application shutdown/cleanup
        """
        if self.conn:
            try:
                # Ensure connection is fully closed
                await self.conn.ensure_closed()
                logger.info("Database connection closed")
            except Exception as e:
                # Log but don't raise - closing is best-effort
                logger.error(f"Error closing connection: {e}")
            finally:
                # Always set to None for clean state
                self.conn = None
