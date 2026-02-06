import os
import json
import shutil
import sys
import time

# This script resets the bot to zero by deleting the database, logs and cache.
# It then recreates fresh, empty files for the database and logs.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RESOURCES_DIR = os.path.join(BASE_DIR, "bot", "resources")

# Add project root to path for imports
sys.path.append(BASE_DIR)

# Attempt to import DatabaseManager (may fail if project structure is broken)
try:
    from bot.core.database import DatabaseManager
except ImportError:
    DatabaseManager = None

def safe_remove(path):
    """Safely remove a file, retrying if locked."""
    if not os.path.exists(path):
        return True
    
    for i in range(3):
        try:
            os.remove(path)
            return True
        except Exception as e:
            if i == 2:
                print(f"⚠ Could not delete {path}: {e}")
                return False
            time.sleep(1)
    return False

def reset():
    print("Resetting bot data to zero...")
    
    # 1. Database
    db_file = os.path.join(RESOURCES_DIR, "database", "tracker.db")
    if os.path.exists(db_file):
        if safe_remove(db_file):
            print(f"✓ Wiped existing database: {db_file}")
    
    # Recreate fresh database
    if DatabaseManager:
        try:
            DatabaseManager(db_file)
            print(f"✓ Created fresh/blank database: {db_file}")
        except Exception as e:
            print(f"⚠ Failed to recreate database: {e}")
    else:
        print("· DatabaseManager not available, skipping recreation.")

    # 2. Logs
    log_file = os.path.join(RESOURCES_DIR, "logs", "bot.log")
    if os.path.exists(log_file):
        if safe_remove(log_file):
            print(f"✓ Wiped existing log file: {log_file}")
    
    # Recreate empty log file
    try:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        with open(log_file, "w") as f:
            f.write("")
        print(f"✓ Created fresh/blank log file: {log_file}")
    except Exception as e:
        print(f"⚠ Failed to recreate log file: {e}")

    # 3. __pycache__
    print("Finding and deleting __pycache__ folders...")
    pycache_count = 0
    for root, dirs, files in os.walk(BASE_DIR):
        if "__pycache__" in dirs:
            pycache_path = os.path.join(root, "__pycache__")
            try:
                shutil.rmtree(pycache_path)
                print(f"✓ Deleted: {pycache_path}")
                pycache_count += 1
            except Exception as e:
                print(f"⚠ Could not delete {pycache_path}: {e}")
    
    if pycache_count == 0:
        print("· No __pycache__ folders found.")

    print("\nSUCCESS: Bot has been reset to zero and initialized with blank data files.")

if __name__ == "__main__":
    reset()
