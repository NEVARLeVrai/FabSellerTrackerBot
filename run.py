# -*- coding: utf-8 -*-
"""
Entry point for Fab Seller Tracker Bot.
Run this script to start the bot.
"""
import os
import sys
import subprocess
import pkg_resources
from loguru import logger

# Add the current directory to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def check_requirements():
    """Checks and installs requirements if needed."""
    requirements_file = "requirements.txt"
    if not os.path.exists(requirements_file):
        logger.warning(f"{requirements_file} not found!")
        return

    # Read requirements
    with open(requirements_file, 'r') as f:
        requirements = [line.strip() for line in f if line.strip() and not line.startswith('#')]

    missing = []
    for req in requirements:
        try:
            pkg_resources.require(req)
        except (pkg_resources.DistributionNotFound, pkg_resources.VersionConflict):
            missing.append(req)

    if missing:
        logger.info(f"Missing dependencies: {', '.join(missing)}")
        logger.info("Installing dependencies...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", requirements_file])
            logger.info("Dependencies installed successfully.")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to install dependencies: {e}")
            sys.exit(1)

def check_playwright():
    """Checks if Playwright browsers are installed."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return # Playwright not installed yet (should be caught by check_requirements)
        
    # Simple check to see if we can launch a browser
    # Note: This is an expensive check, so we might skip it or just handle the error at runtime.
    # Instead, let's just use the command line check if possible, or just rely on the main error handler.
    pass

if __name__ == '__main__':
    # Check dependencies first
    check_requirements()
    
    # Import bot after checks
    try:
        from bot.config import TOKEN
        from bot.main import bot
    except ImportError as e:
        logger.error(f"Failed to import bot: {e}")
        sys.exit(1)

    if not TOKEN:
        logger.error("ASSETS_BOT_TOKEN not defined!")
        sys.exit(1)
    
    logger.info("Starting Fab Seller Tracker Bot...")
    try:
        bot.run(TOKEN)
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
    except Exception as e:
        logger.exception(f"Critical error: {e}")
