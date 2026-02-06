# -*- coding: utf-8 -*-
"""
Configuration for Fab Seller Tracker Bot
"""
import os

# Paths
PATHS = {
    'token_file': "C:/Users/Danie/Mon Drive/Autres/Bot Python Discord/token_fab.txt",
    'data_folder': "./data/",
    'log_file': "./data/logs/bot.log",
    'sellers_file': "sellers_subscriptions.json",
    'products_cache_file': "products_cache.json",
}

# Read token from file
def get_token() -> str:
    """Reads Discord token from file."""
    # 1. Check for token.txt in root
    local_token = "token.txt"
    if os.path.exists(local_token):
        with open(local_token, 'r', encoding='utf-8') as f:
            return f.read().strip()
            
    # 2. Check hardcoded path (Legacy)
    token_path = PATHS['token_file']
    if os.path.exists(token_path):
        with open(token_path, 'r', encoding='utf-8') as f:
            return f.read().strip()
            
    # 3. Check Environment Variable
    return os.environ.get("ASSETS_BOT_TOKEN", "")

TOKEN = get_token()

# Data paths (for compatibility)
DATA_FOLDER = PATHS['data_folder']
SELLERS_FILE = PATHS['sellers_file']
PRODUCTS_CACHE_FILE = PATHS['products_cache_file']
LOG_FILE = PATHS['log_file']

# Default schedule
DEFAULT_CHECK_SCHEDULE = {
    "day": "sunday",
    "hour": 0,
    "minute": 0
}

# Default timezone
DEFAULT_TIMEZONE = "Europe/Paris"

# Days of the week (for scheduler)
WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6
}

# Fab.com URLs
FAB_BASE_URL = "https://www.fab.com"
FAB_SELLERS_URL = f"{FAB_BASE_URL}/sellers/"
FAB_LISTINGS_URL = f"{FAB_BASE_URL}/listings/"

# Delays and limits
SCRAPE_RETRY_COUNT = 3
SCRAPE_DELAY_MIN = 2.0  # seconds between requests
SCRAPE_DELAY_MAX = 5.0
PAGE_LOAD_TIMEOUT = 60000  # ms
SCROLL_DELAY = 1.0  # seconds

# Currency Settings
DEFAULT_CURRENCY = "USD"
CURRENCY_LOCALES = {
    "USD": {"locale": "en-US", "timezone": "America/New_York"},
    "EUR": {"locale": "fr-FR", "timezone": "Europe/Paris"},
    "GBP": {"locale": "en-GB", "timezone": "Europe/London"}
}

# Discord Colors (embeds)
COLOR_NEW_PRODUCT = 0x00FF00  # Green
COLOR_UPDATED_PRODUCT = 0x3498DB  # Blue
COLOR_ERROR = 0xFF0000  # Red
COLOR_INFO = 0x9B59B6  # Purple