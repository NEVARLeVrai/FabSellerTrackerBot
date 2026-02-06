import sqlite3
import json
import os
from datetime import datetime
from typing import List, Optional, Dict
from loguru import logger
from bot.models.models import Product, GuildConfig

class DatabaseManager:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Initializes the database schema."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with self._get_connection() as conn:
            # Guilds table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS guilds (
                    guild_id TEXT PRIMARY KEY,
                    timezone TEXT DEFAULT 'Europe/Paris',
                    language TEXT DEFAULT 'en',
                    currency TEXT DEFAULT 'USD',
                    channel_new INTEGER,
                    channel_updated INTEGER,
                    mentions_enabled INTEGER DEFAULT 0,
                    mentions_new TEXT, -- JSON list
                    mentions_updated TEXT, -- JSON list
                    schedule_day TEXT DEFAULT 'sunday',
                    schedule_hour INTEGER DEFAULT 0,
                    schedule_minute INTEGER DEFAULT 0,
                    schedule_frequency TEXT DEFAULT 'weekly'
                )
            """)
            
            # Subscriptions table (Many-to-Many Guild <-> Seller)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS subscriptions (
                    guild_id TEXT,
                    seller_url TEXT,
                    PRIMARY KEY (guild_id, seller_url)
                )
            """)
            
            # Products table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS products (
                    id TEXT PRIMARY KEY,
                    seller_url TEXT,
                    name TEXT,
                    url TEXT,
                    price_json TEXT, -- Dictionary of currencies
                    image TEXT,
                    ue_versions TEXT,
                    last_update TEXT,
                    published TEXT,
                    changelog TEXT,
                    description TEXT,
                    reviews_count INTEGER,
                    rating REAL,
                    last_seen TEXT,
                    first_seen TEXT
                )
            """)
            
            # Migration/Safe update: check if seller_url exists
            cursor = conn.execute("PRAGMA table_info(products)")
            columns = [row[1] for row in cursor.fetchall()]
            if 'seller_url' not in columns:
                conn.execute("ALTER TABLE products ADD COLUMN seller_url TEXT")
            
            # Seller Cache Info (last check date, etc.)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS seller_cache (
                    seller_url TEXT PRIMARY KEY,
                    last_check TEXT,
                    last_status TEXT,
                    product_count INTEGER DEFAULT 0
                )
            """)
            
            # Migration: add product_count column if missing
            cache_columns = [col[1] for col in conn.execute("PRAGMA table_info(seller_cache)").fetchall()]
            if 'product_count' not in cache_columns:
                conn.execute("ALTER TABLE seller_cache ADD COLUMN product_count INTEGER DEFAULT 0")
            
            conn.commit()

    # --- Guild Methods ---
    def get_guild(self, guild_id: str) -> Optional[GuildConfig]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM guilds WHERE guild_id = ?", (guild_id,)).fetchone()
            if not row: return None
            
            # Get sellers
            sellers = [r['seller_url'] for r in conn.execute("SELECT seller_url FROM subscriptions WHERE guild_id = ?", (guild_id,)).fetchall()]
            
            return GuildConfig(
                guild_id=row['guild_id'],
                sellers=sellers,
                timezone=row['timezone'],
                language=row['language'],
                currency=row['currency'],
                channel_new=row['channel_new'],
                channel_updated=row['channel_updated'],
                mentions_enabled=bool(row['mentions_enabled']),
                mentions_new=json.loads(row['mentions_new'] or '[]'),
                mentions_updated=json.loads(row['mentions_updated'] or '[]'),
                schedule_day=row['schedule_day'],
                schedule_hour=row['schedule_hour'],
                schedule_minute=row['schedule_minute'],
                schedule_frequency=row['schedule_frequency'] if 'schedule_frequency' in row.keys() else 'weekly'
            )

    def get_all_guilds(self) -> List[GuildConfig]:
        """Returns all registered guilds from DB (excluding GLOBAL placeholder)."""
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM guilds WHERE guild_id != 'GLOBAL'").fetchall()
            guilds = []
            for row in rows:
                g = GuildConfig(
                    guild_id=row['guild_id'],
                    timezone=row['timezone'],
                    language=row['language'],
                    currency=row['currency'],
                    channel_new=row['channel_new'],
                    channel_updated=row['channel_updated'],
                    mentions_enabled=bool(row['mentions_enabled']),
                    mentions_new=json.loads(row['mentions_new'] or '[]'),
                    mentions_updated=json.loads(row['mentions_updated'] or '[]'),
                    schedule_day=row['schedule_day'],
                    schedule_hour=row['schedule_hour'],
                    schedule_minute=row['schedule_minute'],
                    schedule_frequency=row['schedule_frequency'] if 'schedule_frequency' in row.keys() else 'weekly'
                )
                guilds.append(g)
            return guilds

    def save_guild(self, config: GuildConfig):
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO guilds 
                (guild_id, timezone, language, currency, channel_new, channel_updated, 
                 mentions_enabled, mentions_new, mentions_updated, schedule_day, schedule_hour, schedule_minute, schedule_frequency)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                config.guild_id, config.timezone, config.language, config.currency,
                config.channel_new, config.channel_updated, int(config.mentions_enabled),
                json.dumps(config.mentions_new), json.dumps(config.mentions_updated),
                config.schedule_day, config.schedule_hour, config.schedule_minute, config.schedule_frequency
            ))
            
            # Sync subscriptions
            conn.execute("DELETE FROM subscriptions WHERE guild_id = ?", (config.guild_id,))
            for seller_url in config.sellers:
                conn.execute("INSERT INTO subscriptions (guild_id, seller_url) VALUES (?, ?)", (config.guild_id, seller_url))
            
            conn.commit()

    # --- Product Methods ---
    def get_seller_products(self, seller_url: str) -> List[Product]:
        """Returns all products for a specific seller from DB."""
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM products WHERE seller_url = ?", (seller_url,)).fetchall()
            products = []
            for row in rows:
                p = Product(
                    id=row['id'],
                    name=row['name'],
                    url=row['url'],
                    seller_url=row['seller_url'],
                    price=json.loads(row['price_json'] or '{}'),
                    image=row['image'],
                    ue_versions=row['ue_versions'],
                    last_update=row['last_update'],
                    published=row['published'],
                    changelog=row['changelog'],
                    description=row['description'],
                    reviews_count=row['reviews_count'],
                    rating=row['rating'],
                    last_seen=row['last_seen'],
                    first_seen=row['first_seen']
                )
                products.append(p)
            return products

    def save_products(self, products: List[Product], seller_url: str = None):
        """Saves or updates products in DB, with optional seller linkage."""
        with self._get_connection() as conn:
            for p in products:
                # Use provided seller_url or fall back to previous one if it exists
                s_url = seller_url
                if not s_url:
                    existing = conn.execute("SELECT seller_url FROM products WHERE id = ?", (p.id,)).fetchone()
                    if existing:
                        s_url = existing['seller_url']

                conn.execute("""
                    INSERT OR REPLACE INTO products
                    (id, seller_url, name, url, price_json, image, ue_versions, last_update, published, 
                     changelog, description, reviews_count, rating, last_seen, first_seen)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    p.id, s_url, p.name, p.url, json.dumps(p.price), p.image, p.ue_versions,
                    p.last_update, p.published, p.changelog, p.description,
                    p.reviews_count, p.rating, p.last_seen, p.first_seen
                ))
            conn.commit()

    def get_product(self, product_id: str) -> Optional[Product]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
            if not row: return None
            
            data = dict(row)
            data['price'] = json.loads(data.pop('price_json'))
            return Product.from_dict(data)

    # --- Global Config ---
    def get_global_currency(self) -> str:
        # We can store this in a special table or a special guild ID
        with self._get_connection() as conn:
            row = conn.execute("SELECT currency FROM guilds WHERE guild_id = 'GLOBAL'").fetchone()
            return row['currency'] if row else "USD"

    def set_global_currency(self, currency: str):
        with self._get_connection() as conn:
            conn.execute("INSERT OR REPLACE INTO guilds (guild_id, currency) VALUES ('GLOBAL', ?)", (currency,))
            conn.commit()

    def update_seller_status(self, seller_url: str, status: str, product_count: int = None):
        """Updates the status, last check timestamp and product count for a seller."""
        with self._get_connection() as conn:
            if product_count is not None:
                conn.execute("""
                    INSERT OR REPLACE INTO seller_cache (seller_url, last_check, last_status, product_count)
                    VALUES (?, ?, ?, ?)
                """, (seller_url, datetime.now().isoformat(), status, product_count))
            else:
                # Keep existing product_count if not provided
                existing = conn.execute("SELECT product_count FROM seller_cache WHERE seller_url = ?", (seller_url,)).fetchone()
                old_count = existing['product_count'] if existing and existing['product_count'] else 0
                conn.execute("""
                    INSERT OR REPLACE INTO seller_cache (seller_url, last_check, last_status, product_count)
                    VALUES (?, ?, ?, ?)
                """, (seller_url, datetime.now().isoformat(), status, old_count))
            conn.commit()
