# -*- coding: utf-8 -*-
"""
Entry point for Fab Seller Tracker Bot.
Run this script to start the bot.
"""
import os
import sys
import subprocess
import importlib.util

# from loguru import logger  <-- Moved to after check_requirements

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

    # Read requirements
    with open(requirements_file, 'r') as f:
        requirements = [line.strip() for line in f if line.strip() and not line.startswith('#')]

    missing = []
    # Use importlib to check if packages are installed (approximate check)
    # or just simple pip install logic. 
    # To be robust against pkg_resources deprecation, let's use a simpler check:
    # try to import the package, or just run pip install if critical ones missing.
    
    # Simple check: try to import check_requirements critical deps
    # But names in requirements.txt (e.g. beautifulsoup4) differ from import name (bs4)
    # Using pkg_resources is easiest for now, but we import it lazily.
    
    try:
        import pkg_resources
    except ImportError:
        # If setuptools/pkg_resources missing, just install everything
        missing = requirements
    else:
        for req in requirements:
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
    except ImportError:
        return # Playwright not installed yet (should be caught by check_requirements)
        
    # Simple check to see if we can launch a browser
    # Note: This is an expensive check, so we might skip it or just handle the error at runtime.
    # Instead, let's just use the command line check if possible, or just rely on the main error handler.
    pass

if __name__ == '__main__':
    # Check dependencies first
    check_requirements()
    
    # Import bot after checks and Install
    try:
        from loguru import logger
        from bot.config import TOKEN
        from bot.main import bot
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
        # Pause on exit if not a clean exit (optional, but good for debugging)
        if sys.exc_info()[0] is not None:
             input("Press Enter to close...")
