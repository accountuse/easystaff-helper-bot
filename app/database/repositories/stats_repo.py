"""
Statistics repository module for user activity tracking.

This module provides database operations for tracking and retrieving
user statistics, including registration data and usage patterns.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any

logger = logging.getLogger(__name__)


class StatsRepository:
    """
    Repository for managing user statistics in database.

    Handles user registration tracking, activity logging, and statistics
    aggregation with automatic database reconnection on connection loss.

    Attributes:
        db (AsyncDatabaseConnection): Async database connection instance

    Example:
        >>> stats_repo = StatsRepository(db_connection)
        >>> await stats_repo.update_user_stats(telegram_user)
        >>> stats = await stats_repo.get_stats()
        >>> print(f"Total users: {stats['total_registered_users']}")
        Total users: 42

    Note:
        All methods use async context manager (get_cursor) which automatically
        handles connection health checks and reconnection via ensure_connected().
    """

    def __init__(self, db) -> None:
        """
        Initialize statistics repository with database connection.

        Args:
            db (AsyncDatabaseConnection): Async database connection instance
                that provides get_cursor() method with auto-reconnect

        Returns:
            None
        """
        self.db = db  # AsyncDatabaseConnection

    """
    async def ping(self):
        # Simple ping to check DB connectivity. (two calls in commands.py)
        # Uses the same ensure_connected mechanism as regular queries.
        try:
            async with self.db.get_cursor() as cur:
                await cur.execute("SELECT 1")
                await cur.fetchone()
            logger.debug("Database ping successful")
            return True
        except Exception as e:
            logger.error(f"Database ping failed: {e}")
            return False
    """

    async def update_user_stats(self, user) -> None:
        """
        Update user registration info and log current usage activity.

        Performs two operations in a single transaction:
        1. UPSERT user record (insert new or update existing)
        2. INSERT usage log entry with current timestamp

        User data is updated on each call, keeping first_usage timestamp
        at the earliest value and updating last_usage to current time.

        Args:
            user: Telegram user object with attributes:
                - id (int): Telegram user ID
                - username (str|None): Telegram username
                - first_name (str|None): User's first name
                - last_name (str|None): User's last name

        Returns:
            None

        Raises:
            Exception: Re-raises database errors after logging

        Example:
            >>> from aiogram.types import User
            >>> user = User(id=123, username="john", first_name="John")
            >>> await stats_repo.update_user_stats(user)
            # User record upserted and usage logged

        Note:
            - Uses UPSERT (INSERT ... ON DUPLICATE KEY UPDATE) for efficiency
            - first_usage preserved with LEAST() to keep earliest timestamp
            - Auto-reconnects on connection loss via get_cursor()
            - Logs success at DEBUG level, errors at ERROR level
        """
        # Get current timestamp for both first_usage/last_usage and usage log
        now = datetime.now()

        # UPSERT query: insert new user or update existing one
        # LEAST() ensures first_usage keeps the earliest timestamp
        upsert_sql = """
            INSERT INTO users (user_id, username, first_name, last_name, first_usage, last_usage)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                username = VALUES(username),
                first_name = VALUES(first_name),
                last_name = VALUES(last_name),
                first_usage = LEAST(first_usage, VALUES(first_usage)),
                last_usage = VALUES(last_usage)
        """

        # Insert usage log entry for statistics tracking
        stat_sql = """
            INSERT INTO user_stats (user_id, usage_datetime)
            VALUES (%s, %s)
        """

        try:
            # Execute both queries in same cursor context (implicit transaction)
            async with self.db.get_cursor() as cur:
                await cur.execute(upsert_sql, (
                    user.id, user.username, user.first_name, user.last_name, now, now
                ))
                await cur.execute(stat_sql, (user.id, now))
            logger.debug(f"Updated stats for user {user.id}")
        except Exception as e:
            logger.error(f"Failed to update stats for user {user.id}: {e}")
            raise

    async def get_stats(self) -> Dict[str, Any]:
        """
        Retrieve aggregated user statistics and activity data.

        Collects comprehensive statistics including:
        - Total registered users count
        - Total unique active users count
        - Top 15 users by activity with detailed breakdowns

        Each user entry includes usage counts for:
        - All time total
        - Today
        - Current month
        - Previous month
        - Last activity timestamp

        Args:
            None

        Returns:
            Dictionary with structure:
                {
                    "total_registered_users": int,
                    "total_unique_users": int,
                    "current_month": str (YYYY-MM format),
                    "active_users": [
                        {
                            "user_id": int,
                            "username": str,
                            "first_name": str,
                            "last_name": str,
                            "total": int,
                            "today": int,
                            "month": int,
                            "prev_month": int,
                            "last_activity": str (YYYY-MM-DD HH:MM:SS or "never")
                        },
                        ...
                    ]
                }

        Raises:
            Exception: Re-raises database errors after logging

        Example:
            >>> stats = await stats_repo.get_stats()
            >>> print(f"Users: {stats['total_registered_users']}")
            >>> for user in stats['active_users'][:3]:
            ...     print(f"{user['username']}: {user['total']} uses")
            Users: 42
            john_doe: 150 uses
            jane_smith: 89 uses

        Note:
            - Returns top 15 users ordered by total usage (descending)
            - Uses correlated subqueries for per-user stats (could be optimized)
            - Auto-reconnects on connection loss via get_cursor()
            - Empty strings for missing username/first_name/last_name
            - "never" string for users without activity (shouldn't happen in practice)
        """
        # Calculate date ranges for statistics
        today = datetime.now().date()
        current_month = datetime.now().strftime("%Y-%m")
        prev_month = (datetime.now().replace(day=1) - timedelta(days=1)).strftime("%Y-%m")

        # Initialize stats structure with default values
        stats = {
            "total_registered_users": 0,
            "total_unique_users": 0,
            "current_month": current_month,
            "active_users": []
        }

        try:
            async with self.db.get_cursor() as cur:
                # Count total registered users in users table
                await cur.execute("SELECT COUNT(*) FROM users")
                stats["total_registered_users"] = (await cur.fetchone())[0]

                # Count unique users who have activity logged
                await cur.execute("SELECT COUNT(DISTINCT user_id) FROM user_stats")
                stats["total_unique_users"] = (await cur.fetchone())[0]

                # Fetch top 15 active users with detailed statistics
                # Uses correlated subqueries for per-user aggregations
                await cur.execute("""
                    SELECT
                        u.user_id,
                        u.username,
                        u.first_name,
                        u.last_name,
                        (SELECT COUNT(*) FROM user_stats WHERE user_id = u.user_id) as total_usage,
                        (SELECT COUNT(*) FROM user_stats
                         WHERE user_id = u.user_id AND DATE(usage_datetime) = %s) as today_usage,
                        (SELECT COUNT(*) FROM user_stats
                         WHERE user_id = u.user_id AND DATE_FORMAT(usage_datetime, '%%Y-%%m') = %s) as current_month_usage,
                        (SELECT COUNT(*) FROM user_stats
                         WHERE user_id = u.user_id AND DATE_FORMAT(usage_datetime, '%%Y-%%m') = %s) as prev_month_usage,
                        MAX(us.usage_datetime) as last_activity
                    FROM users u
                    LEFT JOIN user_stats us ON u.user_id = us.user_id
                    GROUP BY u.user_id
                    ORDER BY total_usage DESC
                    LIMIT 15
                """, (today, current_month, prev_month))

                # Transform query results into dictionary format
                rows = await cur.fetchall()
                for r in rows:
                    stats["active_users"].append({
                        "user_id": r[0],
                        "username": r[1] or "",  # Empty string if NULL
                        "first_name": r[2] or "",
                        "last_name": r[3] or "",
                        "total": r[4],
                        "today": r[5],
                        "month": r[6],
                        "prev_month": r[7],
                        "last_activity": r[8].strftime("%Y-%m-%d %H:%M:%S") if r[8] else "never"
                    })

            logger.debug("Stats retrieved successfully")
        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            raise

        return stats
