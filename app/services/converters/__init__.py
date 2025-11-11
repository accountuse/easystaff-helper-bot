"""
Currency conversion services package.

This package provides exchange rate fetching services from
multiple sources (XE.com, Easystaff) with different methods
(web scraping, browser automation).
"""

from .xe_service import XeConverterService
from .easystaff_service import EasystaffService

__all__ = [
    'XeConverterService',
    'EasystaffService',
]
