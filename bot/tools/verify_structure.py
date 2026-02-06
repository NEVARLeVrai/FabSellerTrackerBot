import os
import sys
from loguru import logger

def verify():
    print("=== FINAL PROJECT VERIFICATION ===")
    
    # 1. Path Setup
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    sys.path.append(BASE_DIR)
    print(f"✓ Base directory: {BASE_DIR}")

    # 2. Module Imports
    print("\n--- Testing Module Imports ---")
    try:
        from bot.core import config
        print("✓ bot.core.config imported successfully")
        from bot.core import database
        print("✓ bot.core.database imported successfully")
        from bot.core import lang
        print("✓ bot.core.lang imported successfully")
        from bot.core import main
        print("✓ bot.core.main imported successfully")
        from bot.services import scraper
        print("✓ bot.services.scraper imported successfully")
        from bot.models import models
        print("✓ bot.models.models imported successfully")
    except ImportError as e:
        print(f"❌ IMPORT ERROR: {e}")
        return

    # 3. Config Path Verification
    print("\n--- Verifying Config Paths ---")
    from bot.core.config import PATHS, RESOURCES_DIR, JSON_DIR, DATABASE_DIR, LOGS_DIR
    
    paths_to_check = {
        "Resources Directory": RESOURCES_DIR,
        "JSON Directory": JSON_DIR,
        "Database Directory": DATABASE_DIR,
        "Logs Directory": LOGS_DIR,
        "Database File": os.path.join(DATABASE_DIR, "tracker.db"),
        "Sellers File": PATHS['sellers_file'],
        "Version File": PATHS['version_file'],
        "Translations (EN)": os.path.join(RESOURCES_DIR, "lang", "en.json"),
        "Translations (FR)": os.path.join(RESOURCES_DIR, "lang", "fr.json"),
    }

    errors = 0
    for name, path in paths_to_check.items():
        if os.path.exists(path):
            print(f"✓ {name}: {path}")
        else:
            print(f"❌ MISSING: {name} at {path}")
            errors += 1

    # 4. Bot Initialization Test
    print("\n--- Testing Bot Initialization ---")
    try:
        from bot.core.main import bot
        print(f"✓ Bot instance created: {bot}")
        print(f"✓ Database manager linked: {bot.db}")
        print(f"✓ Database path in manager: {bot.db.db_path}")
        if os.path.abspath(bot.db.db_path) == os.path.abspath(os.path.join(DATABASE_DIR, "tracker.db")):
            print("✓ Database path synchronization OK")
        else:
            print(f"⚠ Database path mismatch: {bot.db.db_path} vs {os.path.join(DATABASE_DIR, 'tracker.db')}")
            errors += 1
    except Exception as e:
        print(f"❌ INITIALIZATION ERROR: {e}")
        errors += 1

    if errors == 0:
        print("\n🏆 SUCCESS: All internal links and paths are correct!")
    else:
        print(f"\n⚠️ FAILED: {errors} errors found in project links.")

if __name__ == "__main__":
    verify()
