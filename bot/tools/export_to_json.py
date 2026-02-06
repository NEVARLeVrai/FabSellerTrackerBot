import sqlite3
import json
import os

db_path = "bot/resources/database/tracker.db"
export_path = "bot/resources/database/tracker_export.json"

def export_db():
    if not os.path.exists(db_path):
        print(f"Database {db_path} not found.")
        return

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    data = {}
    
    # Export all tables
    tables = ["guilds", "subscriptions", "products", "seller_cache"]
    for table in tables:
        try:
            rows = conn.execute(f"SELECT * FROM {table}").fetchall()
            data[table] = [dict(row) for row in rows]
        except sqlite3.OperationalError:
            data[table] = []
            
    with open(export_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)
        
    conn.close()
    print(f"Database exported successfully to {export_path}")

if __name__ == "__main__":
    export_db()
