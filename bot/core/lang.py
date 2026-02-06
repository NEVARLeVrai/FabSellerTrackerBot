# -*- coding: utf-8 -*-
"""
Language Manager for Fab Seller Tracker Bot
Handles loading and retrieving translations from JSON files.
"""
import os
import json
from loguru import logger

# Default language
DEFAULT_LANGUAGE = "en"

# Cache for loaded languages
_languages_cache: dict = {}
_available_languages: list = []


def _get_lang_dir() -> str:
    """Get the language files directory path."""
    # current file: bot/core/lang.py
    # target: bot/resources/lang
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_dir, "resources", "lang")


def load_languages() -> None:
    """Load all available language files into cache."""
    global _languages_cache, _available_languages
    
    lang_dir = _get_lang_dir()
    _languages_cache = {}
    _available_languages = []
    
    if not os.path.exists(lang_dir):
        logger.warning(f"Language directory not found: {lang_dir}")
        return
    
    for filename in os.listdir(lang_dir):
        if filename.endswith(".json"):
            lang_code = filename[:-5]  # Remove .json
            filepath = os.path.join(lang_dir, filename)
            
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    _languages_cache[lang_code] = json.load(f)
                    _available_languages.append(lang_code)
                    logger.info(f"Loaded language: {lang_code}")
            except Exception as e:
                logger.error(f"Failed to load language {lang_code}: {e}")
    
    logger.info(f"Available languages: {', '.join(_available_languages)}")


def get_available_languages() -> list:
    """Get list of available language codes."""
    if not _available_languages:
        load_languages()
    return _available_languages.copy()


def get_language_name(lang_code: str) -> str:
    """Get the display name of a language."""
    if lang_code in _languages_cache:
        return _languages_cache[lang_code].get("lang_name", lang_code)
    return lang_code


def get_text(key: str, lang: str = DEFAULT_LANGUAGE, **kwargs) -> str:
    """
    Get a translated text by key.
    
    Args:
        key: The translation key
        lang: Language code (e.g., 'en', 'fr')
        **kwargs: Format arguments for the string
        
    Returns:
        The translated and formatted string
    """
    if not _languages_cache:
        load_languages()
    
    # Try requested language, then default, then return key
    translations = _languages_cache.get(lang) or _languages_cache.get(DEFAULT_LANGUAGE) or {}
    text = translations.get(key, key)
    
    # Format with kwargs if provided
    if kwargs:
        try:
            text = text.format(**kwargs)
        except KeyError as e:
            logger.warning(f"Missing format key {e} for {key}")
    
    return text


def t(key: str, lang: str = DEFAULT_LANGUAGE, **kwargs) -> str:
    """Shorthand for get_text."""
    return get_text(key, lang, **kwargs)


# Load languages on import
load_languages()
