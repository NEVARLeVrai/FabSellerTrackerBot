# -*- coding: utf-8 -*-
"""
Entry point for Fab Seller Tracker Bot.
Run this script to start the bot.
"""
import os
import sys
import subprocess
import importlib.util

# Add the current directory to sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BASE_DIR)
os.chdir(BASE_DIR)  # Force CWD to script directory

def check_requirements():
    """Checks and installs requirements if needed."""
    requirements_file = "requirements.txt"
    if not os.path.exists(requirements_file):
        print(f"{requirements_file} not found!")
        return

    with open(requirements_file, 'r') as f:
        requirements = [line.strip() for line in f if line.strip() and not line.startswith('#')]

    missing = []
    try:
        import pkg_resources
    except ImportError:
        missing = requirements
    else:
        for req in requirements:
            if req.startswith("#") or not req.strip():
                continue
            try:
                pkg_resources.require(req)
            except (pkg_resources.DistributionNotFound, pkg_resources.VersionConflict):
                missing.append(req)

    if missing:
        print(f"Missing dependencies: {', '.join(missing)}")
        print("Installing dependencies...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", requirements_file])
            print("Dependencies installed successfully.")
        except subprocess.CalledProcessError as e:
            print(f"Failed to install dependencies: {e}")
            input("Press Enter to close...")
            sys.exit(1)

def check_playwright():
    """Checks if Playwright browsers are installed."""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            try:
                browser = p.firefox.launch(headless=True)
                browser.close()
                print("Playwright browsers are ready.")
            except Exception as e:
                print(f"Browser check failed ({e}). Installing Firefox...")
                subprocess.check_call([sys.executable, "-m", "playwright", "install", "firefox"])
                print("Playwright browsers installed successfully.")
    except Exception as e:
        print(f"Warning: Failed to check Playwright: {e}")

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
    except ImportError as e:
        print(f"Failed to import bot: {e}")
        input("Press Enter to close...")
        sys.exit(1)

    if not TOKEN:
        logger.error("ASSETS_BOT_TOKEN not defined!")
        logger.error("Please set it in token.txt or config.py")
        input("Press Enter to close...")
        sys.exit(1)
    
    logger.info("Starting Fab Seller Tracker Bot...")
    try:
        bot.run(TOKEN)
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
    except Exception as e:
        logger.exception(f"Critical error: {e}")
        input("Press Enter to close...")
    finally:
        if sys.exc_info()[0] is not None:
             input("Press Enter to close...")
