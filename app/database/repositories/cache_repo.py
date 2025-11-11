"""
Cache repository module for exchange rate storage.

This module provides file-based caching functionality for exchange rates,
using JSON format with UTF-8 encoding for persistence.
"""

import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict
from config.settings import Settings


class CacheRepository:
    """
    Repository for managing exchange rate cache in JSON format.

    Handles reading and writing exchange rate data to a local JSON file,
    providing simple persistence layer with automatic timestamp tracking.

    Attributes:
        cache_path (Path): Path to the JSON cache file

    Example:
        >>> cache = CacheRepository()
        >>> cache.save(85.5)
        True
        >>> data = cache.load()
        >>> print(data['rate'])
        85.5
    """

    def __init__(self, cache_path: Path = Settings.CACHE_FILE) -> None:
        """
        Initialize cache repository with specified file path.

        Args:
            cache_path: Path to JSON cache file (default from Settings.CACHE_FILE)

        Returns:
            None
        """
        self.cache_path = cache_path

    def load(self) -> Optional[Dict]:
        """
        Load cached exchange rate data from JSON file.

        Reads the cache file and returns parsed JSON data containing
        the exchange rate and update timestamp. Returns None if file
        doesn't exist or cannot be read.

        Args:
            None

        Returns:
            Dictionary with 'rate' (float) and 'updated_at' (str) keys,
            or None if cache doesn't exist or reading failed

        Example:
            >>> cache = CacheRepository()
            >>> data = cache.load()
            >>> if data:
            ...     print(f"Rate: {data['rate']}, Updated: {data['updated_at']}")
            Rate: 85.5, Updated: 2025-11-11T09:30:00.000000+00:00

        Note:
            - Returns None silently if file doesn't exist (not an error)
            - Prints error message to stdout for JSON/IO errors
            - Assumes cache file contains valid JSON with expected structure
        """
        # Return None if cache file doesn't exist yet (first run)
        if not self.cache_path.exists():
            return {}

        try:
            # Read and parse JSON cache file with UTF-8 encoding
            with open(self.cache_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, IOError) as e:
            # Print error but don't raise - allow graceful degradation
            print(f"Cache read error: {e}")
            return {}


    def save(self, rate: float) -> bool:
        """
        Save exchange rate to cache file with current timestamp.

        Creates a new cache entry with the provided rate and current UTC
        timestamp, writing it to the JSON file. Overwrites existing cache.

        Args:
            rate: Exchange rate value to cache (e.g., 85.5)

        Returns:
            True if cache was saved successfully, False on error
        Raises:
            None (catches IOError internally and returns False)

        Example:
            >>> cache = CacheRepository()
            >>> success = cache.save(85.5)
            >>> if success:
            ...     print("Rate cached successfully")
            Rate cached successfully

        Note:
            - Uses UTC timezone for timestamp to avoid timezone issues
            - Pretty-prints JSON with 2-space indentation for readability
            - Preserves Unicode characters (ensure_ascii=False)
            - Prints error message to stdout on failure
        """
        # Prepare cache data with rate and ISO-formatted UTC timestamp
        data = {
            "rate": rate,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }

        try:
            # ensure parent directories exist before writing
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)

            # Write JSON to file with UTF-8 encoding and formatting
            with open(self.cache_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except IOError as e:
            # Print error but don't raise - return False to indicate failure
            print(f"Cache write error: {e}")
            return False
