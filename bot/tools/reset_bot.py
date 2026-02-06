import os
import json
import shutil
import sys

# This script resets the bot to zero by deleting the database, logs and cache.
# It then recreates fresh, empty files for the database and logs.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RESOURCES_DIR = os.path.join(BASE_DIR, "bot", "resources")

# Add project root to path for imports
sys.path.append(BASE_DIR)

from bot.core.database import DatabaseManager

def reset():
    print("Resetting bot data to zero...")
    
    # 1. Database
    db_file = os.path.join(RESOURCES_DIR, "database", "tracker.db")
    if os.path.exists(db_file):
        os.remove(db_file)
        print(f"✓ Wiped existing database: {db_file}")
    
    # Recreate fresh database
    try:
        DatabaseManager(db_file)
        print(f"✓ Created fresh/blank database: {db_file}")
    except Exception as e:
        print(f"⚠ Failed to recreate database: {e}")

    # 2. Logs
    log_file = os.path.join(RESOURCES_DIR, "logs", "bot.log")
    if os.path.exists(log_file):
        os.remove(log_file)
        print(f"✓ Wiped existing log file: {log_file}")
    
    # Recreate empty log file
    try:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        with open(log_file, "w") as f:
            f.write("")
        print(f"✓ Created fresh/blank log file: {log_file}")
    except Exception as e:
        print(f"⚠ Failed to recreate log file: {e}")

    # 3. JSON Cache / Subs
    json_dir = os.path.join(RESOURCES_DIR, "json")
    if os.path.exists(json_dir):
        # Product cache (Old)
        prod_cache = os.path.join(json_dir, "products_cache.json")
        if os.path.exists(prod_cache):
            os.remove(prod_cache)
            print(f"✓ Deleted legacy cache: {prod_cache}")
            
        # Subscriptions
        subs_file = os.path.join(json_dir, "sellers_subscriptions.json")
        if os.path.exists(subs_file):
            with open(subs_file, "w", encoding="utf-8") as f:
                json.dump({}, f)
            print(f"✓ Reset subscriptions file: {subs_file}")

    # 4. __pycache__
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
