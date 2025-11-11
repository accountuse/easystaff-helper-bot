"""
Data repositories package.

This package provides data access layer repositories for
cache management and user statistics tracking.
"""

from .cache_repo import CacheRepository
from .stats_repo import StatsRepository

__all__ = [
    'CacheRepository',
    'StatsRepository',
]
