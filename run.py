# -*- coding: utf-8 -*-
"""
Entry point for Fab Seller Tracker Bot.
Run this script to start the bot.
"""
import os
import sys
import subprocess
import importlib.util
import json

# Add the current directory to sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BASE_DIR)
os.chdir(BASE_DIR)  # Force CWD to script directory

# Early translation function (before dependencies are installed)
def get_early_text(key: str, **kwargs) -> str:
    """Get translation before dependencies are installed."""
    try:
        lang_file = os.path.join(BASE_DIR, "bot", "resources", "lang", "fr.json")
        with open(lang_file, "r", encoding="utf-8") as f:
            translations = json.load(f)
        text = translations.get(key, key)
        if kwargs:
            text = text.format(**kwargs)
        return text
    except:
        return key

def check_requirements():
    """Checks and installs requirements if needed."""
    requirements_file = "requirements.txt"
    if not os.path.exists(requirements_file):
        print(get_early_text("run_req_not_found", requirements=requirements_file))
        return

    with open(requirements_file, 'r') as f:
        requirements = [line.strip() for line in f if line.strip() and not line.startswith('#')]

    missing = []
    from importlib.metadata import distributions
    installed = {dist.metadata['Name'].lower(): dist.version for dist in distributions()}

    for req in requirements:
        if req.startswith("#") or not req.strip():
            continue
        # Extract package name (before any version specifier)
        pkg_name = req.split('>=')[0].split('<=')[0].split('==')[0].split('~=')[0].split('[')[0].strip().lower()
        if pkg_name not in installed:
            missing.append(req)

    if missing:
        print(get_early_text("run_missing_deps", deps=', '.join(missing)))
        print(get_early_text("run_installing_deps"))
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", requirements_file])
            print(get_early_text("run_deps_installed"))
        except subprocess.CalledProcessError as e:
            print(get_early_text("run_deps_install_error", error=e))
            input(get_early_text("run_press_enter"))
            sys.exit(1)

def check_playwright():
    """Checks if Playwright browsers are installed."""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            try:
                browser = p.firefox.launch(headless=True)
                browser.close()
                print(get_early_text("run_playwright_ready"))
            except Exception as e:
                print(get_early_text("run_playwright_check_failed", error=e))
                subprocess.check_call([sys.executable, "-m", "playwright", "install", "firefox"])
                print(get_early_text("run_playwright_installed"))
    except Exception as e:
        print(get_early_text("run_playwright_warning", error=e))

if __name__ == '__main__':
    # Check dependencies first
    check_requirements()
    # Check Playwright browsers
    check_playwright()
    
    # Import bot after checks
    try:
        from loguru import logger
        from bot.core.config import TOKEN
        from bot.core.main import bot
        from bot.core.lang import t
    except ImportError as e:
        print(get_early_text("run_import_error", error=e))
        input(get_early_text("run_press_enter"))
        sys.exit(1)

    if not TOKEN:
        logger.error(t("run_token_missing"))
        logger.error(t("run_token_hint"))
        input(t("run_press_enter"))
        sys.exit(1)

    logger.info(t("run_starting"))
    try:
        bot.run(TOKEN)
    except KeyboardInterrupt:
        logger.info(t("run_stopped_user"))
    except Exception as e:
        logger.exception(t("run_critical_error", error=e))
        input(t("run_press_enter"))
    finally:
        if sys.exc_info()[0] is not None:
             input(t("run_press_enter"))
