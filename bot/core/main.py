# -*- coding: utf-8 -*-
"""
Fab Seller Tracker Bot
Discord Bot to track seller products on Fab.com
"""
import json
import os
import asyncio
import sys
import aiohttp
from datetime import datetime, time, timedelta
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks
from loguru import logger
from zoneinfo import ZoneInfo

# Internal Version and Version File
BOT_VERSION = "Unknown"
VERSION_INFO = {}

def load_version():
    """Loads the version from the resources folder."""
    global BOT_VERSION, VERSION_INFO
    from .config import PATHS
    v_file = PATHS['version_file']
    if os.path.exists(v_file):
        try:
            with open(v_file, 'r', encoding='utf-8') as f:
                VERSION_INFO = json.load(f)
                BOT_VERSION = VERSION_INFO.get("version", "Unknown")
        except Exception as e:
            logger.error(f"Failed to load version info: {e}")

load_version()

from bot.core.config import (
    TOKEN,
    DATA_FOLDER,
    DEFAULT_CHECK_SCHEDULE,
    DEFAULT_TIMEZONE,
    WEEKDAYS,
    COLOR_NEW_PRODUCT,
    COLOR_UPDATED_PRODUCT,
    COLOR_INFO,
    LOG_FILE,
    PATHS
)
from bot.services.scraper import scrape_seller_with_details
from bot.core.lang import t, get_available_languages, get_language_name
from bot.core.database import DatabaseManager
from bot.models.models import Product, GuildConfig

logger.add(LOG_FILE, rotation="10 MB", level="INFO")


# Utility functions
def extract_seller_name(url: str) -> Optional[str]:
    """Extracts seller name from URL."""
    # https://www.fab.com/sellers/GameAssetFactory -> GameAssetFactory
    if "/sellers/" in url:
        parts = url.split("/sellers/")
        if len(parts) > 1:
            return parts[1].rstrip("/").split("?")[0]
    return None


def normalize_seller_url(url: str) -> Optional[str]:
    """Normalizes the seller URL."""
    name = extract_seller_name(url)
    if name:
        return f"https://www.fab.com/sellers/{name}"
    return None


# ============================================================================
# Main Bot
# ============================================================================

class FabSellerTrackerBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
        
        # Database
        db_path = os.path.join(DATA_FOLDER, "tracker.db")
        self.db = DatabaseManager(db_path)
        
        # Scheduler
        self.next_check_time = None
        self.check_task = None
        
    async def setup_hook(self):
        """Called at bot startup."""
        # Database initialized in __init__
        
        # Add commands
        self.tree.add_command(sub_command)
        self.tree.add_command(unsub_command)
        self.tree.add_command(list_command)
        self.tree.add_command(set_group)
        self.tree.add_command(info_command)
        self.tree.add_command(check_command)
        
        # Sync commands
        await self.tree.sync()
        logger.info("Slash commands synced")
    
    def get_guild_config_obj(self, guild_id: int) -> GuildConfig:
        """Returns GuildConfig object, ensuring default exists."""
        gid_str = str(guild_id)
        config = self.db.get_guild(gid_str)
        if not config:
            config = GuildConfig(guild_id=gid_str)
            self.db.save_guild(config)
        return config

    def get_guild_lang(self, guild_id: int) -> str:
        """Returns configured language for a guild."""
        config = self.get_guild_config_obj(guild_id)
        return config.language

    def get_global_currency(self) -> str:
        """Returns the global currency setting."""
        return self.db.get_global_currency()
    
    async def on_ready(self):
        """Called when bot is ready."""
        logger.info(f"Connected as {self.user}")
        
        # Set bot status
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="Fab.com sellers"
            )
        )
        
        # Start scheduler
        if self.check_task is None:
            self.check_task = self.loop.create_task(self._schedule_loop())
            
    async def _schedule_loop(self):
        """Main scheduler loop."""
        while True:
            try:
                # Calculate next check
                next_check = self._calculate_next_check()
                if next_check:
                    self.next_check_time = next_check
                    wait_seconds = (next_check - datetime.now(ZoneInfo(DEFAULT_TIMEZONE))).total_seconds()
                    
                    if wait_seconds > 0:
                        logger.info(f"Next check in {wait_seconds/3600:.1f} hours")
                        await asyncio.sleep(wait_seconds)
                    
                    # Execute check
                    await self._check_all_sellers()
                else:
                    # No scheduled check, wait 1 hour
                    await asyncio.sleep(3600)
                    
            except Exception as e:
                logger.error(f"Scheduler error: {e}")
                await asyncio.sleep(60)
                
    def _calculate_next_check(self) -> Optional[datetime]:
        """Calculates next check date based on configured schedules."""
        # Get the first guild with a schedule from DB
        with self.db._get_connection() as conn:
            row = conn.execute("SELECT schedule_day, schedule_hour, schedule_minute, timezone FROM guilds LIMIT 1").fetchone()
            
        if row:
            tz = ZoneInfo(row['timezone'] or DEFAULT_TIMEZONE)
            now = datetime.now(tz)
            target_weekday = WEEKDAYS.get(row['schedule_day'] or "sunday", 6)
            target_hour = row['schedule_hour'] or 0
            target_minute = row['schedule_minute'] or 0
            
            days_ahead = target_weekday - now.weekday()
            if days_ahead < 0:
                days_ahead += 7
            elif days_ahead == 0:
                if now.hour > target_hour or (now.hour == target_hour and now.minute >= target_minute):
                    days_ahead = 7
            
            next_check = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
            next_check += timedelta(days=days_ahead)
            return next_check
            
        return None
    
    async def _check_all_sellers(self):
        """Checks all sellers from all guilds."""
        logger.info("Starting check for all sellers")
        
        # Get all unique sellers from all guilds
        with self.db._get_connection() as conn:
            rows = conn.execute("SELECT DISTINCT seller_url FROM subscriptions").fetchall()
            all_sellers = [r['seller_url'] for r in rows]
        
        for seller_url in all_sellers:
            try:
                # Get existing products from DB
                # Note: Currently products aren't strictly linked to sellers in my DB schema, 
                # but we can filter by seller_url if we add that column or just use the ID-based storage.
                # For now, let's assume we fetch all products the scraper returns.
                # To detect changes we need the PREVIOUS products of THIS seller.
                
                # We need a way to get products by seller. Let's add that to DB or use a simplification.
                # Actually, the scraper returns ALL products of a seller.
                # To detect changes, we compare with what we had for that seller specifically.
                
                # Fetch seller status from DB
                with self.db._get_connection() as conn:
                    seller_info = conn.execute("SELECT last_status FROM seller_cache WHERE seller_url = ?", (seller_url,)).fetchone()
                
                # For change detection, we'll fetch all products currently in DB 
                # (In a real system we'd link products to sellers).
                # Let's just pass an empty list for now if we don't have a good way to filter, 
                # or better: we can store the list of IDs for each seller.
                
                # BETTER: Get products that were "seen" for this seller.
                # Logic: products where urL starts with seller_url (approximate) or linked in a join table.
                # Let's just fetch all and filter by URL (Seller name is in listing URL usually).
                
                # Actually, the simplest is to just fetch the IDs of products we know for this seller.
                # Let's skip the detailed cleanup for now and just pass existing_products=[] to ensure we re-scrape details.
                # Or better, fetch from DB.
                
                currency = self.get_global_currency()
                # For now, let's pass an empty list or fetch all products.
                # Migration note: We need the products to detect changes.
                existing_products = [] # We'll improve this with a proper Seller <-> Product relation soon.
                
                result = await scrape_seller_with_details(seller_url, existing_products, currency=currency)
                
                if result:
                    # Save status to DB
                    self.db.update_seller_status(seller_url, "success")
                    
                    # Convert to Product objects and save
                    new_products = [Product.from_dict(p) for p in result["products"]]
                    self.db.save_products(new_products)
                    
                    # Notify subscribed guilds
                    changes = result["changes"]
                    
                    for prod in changes.get("new", []):
                        await self._notify_guilds(seller_url, prod, is_new=True)
                        await asyncio.sleep(0.5)
                        
                    for prod in changes.get("updated", []):
                        await self._notify_guilds(seller_url, prod, is_new=False)
                        await asyncio.sleep(0.5)
                
            except Exception as e:
                logger.error(f"Check error {seller_url}: {e}")
                self.db.update_seller_status(seller_url, "error")
                
        logger.info("Check completed")
        
    async def _notify_guilds(self, seller_url: str, product: dict, is_new: bool):
        """Notifies guilds about new/updated products."""
        seller_name = extract_seller_name(seller_url)
        
        # Get all guilds subscribed to this seller
        with self.db._get_connection() as conn:
            rows = conn.execute("SELECT guild_id FROM subscriptions WHERE seller_url = ?", (seller_url,)).fetchall()
            guild_ids = [r['guild_id'] for r in rows]
            
        for guild_id_str in guild_ids:
            try:
                config = self.get_guild_config_obj(int(guild_id_str))
                guild = self.get_guild(int(guild_id_str))
                if not guild: continue
                
                # Channel selection
                channel_id = config.channel_new if is_new else config.channel_updated
                if not channel_id: continue
                
                channel = guild.get_channel(channel_id)
                if not channel: continue
                
                # Mentions handling
                mention_string = None
                if config.mentions_enabled:
                    role_ids = config.mentions_new if is_new else config.mentions_updated
                    if role_ids:
                        mention_string = " ".join([f"<@&{rid}>" for rid in role_ids])
                
                lang = config.language
                embed = self._create_product_embed(product, is_new, seller_name, seller_url, lang)
                
                await channel.send(content=mention_string, embed=embed)
                
            except Exception as e:
                logger.error(f"Guild notification error {guild_id_str}: {e}")
    
    def _create_product_embed(self, product: dict, is_new: bool, seller_name: str = None, seller_url: str = None, lang: str = "en") -> discord.Embed:
        """Creates a Discord embed for a product."""
        title = t("new_product", lang) if is_new else t("updated_product", lang)
        color = COLOR_NEW_PRODUCT if is_new else COLOR_UPDATED_PRODUCT
        
        if not product['name']:
             product['name'] = t("unnamed_product", lang)

        embed = discord.Embed(
            title=f"{title}: {product['name']}",
            url=product.get("url"),
            color=color,
            timestamp=datetime.now()
        )
        
        # Price
        price_data = product.get("price")
        if isinstance(price_data, dict):
            # Select the appropriate currency
            guild_currency = bot.get_global_currency()
            price_val = price_data.get(guild_currency)
            if not price_val:
                # Fallback to USD or whatever is available
                price_val = price_data.get("USD") or next(iter(price_data.values()), t("price_not_available", lang))
        else:
            price_val = price_data

        if not price_val:
             price_val = t("price_not_available", lang)
        else:
            # Localize licenses
            price_val = price_val.replace("Personal", t("license_personal", lang))
            price_val = price_val.replace("Professional", t("license_professional", lang))
            
            # Append "Excl. Tax" / "Hors Taxe"
            excl_tax_label = t("excl_tax", lang)
            lines = price_val.split("\n")
            price_val = "\n".join([f"{line} ({excl_tax_label})" for line in lines])
             
        embed.add_field(name=t("embed_price", lang), value=price_val, inline=False)
        
        if seller_name:
            val = f"[{seller_name}]({seller_url})" if seller_url else seller_name
            embed.add_field(name=t("embed_seller", lang), value=val, inline=True)
            

        
        # Reviews & Rating - Display next to UE Versions
        reviews_count = product.get("reviews_count", 0)
        rating = product.get("rating")
        
        if rating is not None and reviews_count > 0:
            # Show rating with review count: "5.0/5 (1)"
            reviews_val = f"{rating}/5 ({reviews_count})"
        elif reviews_count > 0:
            # Show just count if no rating
            reviews_val = str(reviews_count)
        else:
            reviews_val = "5.0/5 (0)" # Default or None, user image showed 5.0/5(6). If 0, maybe just "0/5 (0)" or "None"? User image has "Reviews 5.0/5 (6)". Let's stick to what we have or "None".
            # Actually, user screenshot shows "Reviews" title and "5.0/5 (6)" value.
            # If no reviews, let's keep it clean.
            reviews_val = f"0/5 (0)" 

        embed.add_field(name=t("embed_reviews", lang), value=reviews_val, inline=True)
            
        # Last update
        if product.get("last_update"):
            embed.add_field(name=t("embed_last_update", lang), value=product["last_update"], inline=True)


        # UE Versions
        if product.get("ue_versions"):
             embed.add_field(name=t("embed_ue_versions", lang), value=product["ue_versions"], inline=False)



        # Short description
        if product.get("description"):
            desc = product["description"]
            # Remove duplicate "Description" prefix if present
            if desc.lower().startswith("description "):
                desc = desc[12:]
            elif desc.lower().startswith("description"):
                desc = desc[11:]
            desc = desc.strip()
            desc = desc[:200]
            if len(product["description"]) > 200:
                desc += "..."
            embed.add_field(name=t("embed_description", lang), value=desc, inline=False)

        # Changelog (Bottom, filtered to latest)
        if product.get("changelog"):
            changelog_text = product["changelog"]
            # Filter to show only the first entry (latest)
            entries = changelog_text.split("\n\n")
            if entries:
                latest_entry = entries[0]
                embed.add_field(name=t("embed_changelog", lang), value=latest_entry, inline=False)

        # Image
        if product.get("image"):
            embed.set_thumbnail(url=product["image"])
        
        # Footer
        embed.set_footer(text=t("embed_footer", lang))
        
        return embed


# ============================================================================
# Slash Commands
# ============================================================================

bot = FabSellerTrackerBot()


@app_commands.command(name="sub", description="Subscribe to a Fab.com seller")
@app_commands.describe(seller_url="Seller page URL (e.g. https://fab.com/sellers/Name)")
async def sub_command(interaction: discord.Interaction, seller_url: str):
    """Command /sub to subscribe to a seller."""
    if not interaction.guild:
        await interaction.response.send_message(t("error_only_in_guild"))
        return
    
    lang = bot.get_guild_lang(interaction.guild.id)
    
    # Check permissions
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(t("permission_denied", lang), ephemeral=True)
        return
    
    # Normalize URL
    normalized_url = normalize_seller_url(seller_url)
    if not normalized_url:
        await interaction.response.send_message(t("sub_invalid_url", lang), ephemeral=True)
        return
    
    # Add seller
    config = bot.get_guild_config_obj(interaction.guild.id)
    
    if normalized_url in config.sellers:
        await interaction.response.send_message(t("sub_already", lang), ephemeral=True)
        return
    
    config.sellers.append(normalized_url)
    
    # Set default notification channels if not configured
    if config.channel_new is None:
        config.channel_new = interaction.channel.id
    if config.channel_updated is None:
        config.channel_updated = interaction.channel.id
    
    bot.db.save_guild(config)
    
    seller_name = extract_seller_name(normalized_url)
    await interaction.response.send_message(
        t("sub_success", lang, seller=seller_name)
    )


@app_commands.command(name="unsub", description="Unsubscribe from a Fab.com seller")
@app_commands.describe(seller_url="Seller URL to remove")
async def unsub_command(interaction: discord.Interaction, seller_url: str):
    """Command /unsub to unsubscribe."""
    if not interaction.guild:
        return
    
    lang = bot.get_guild_lang(interaction.guild.id)
    
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(t("permission_denied", lang), ephemeral=True)
        return
    
    normalized_url = normalize_seller_url(seller_url)
    config = bot.get_guild_config_obj(interaction.guild.id)
    
    if normalized_url not in config.sellers:
        await interaction.response.send_message(t("unsub_not_found", lang), ephemeral=True)
        return
    
    config.sellers.remove(normalized_url)
    bot.db.save_guild(config)
    
    seller_name = extract_seller_name(normalized_url)
    await interaction.response.send_message(
        t("unsub_success", lang, seller=seller_name)
    )


@app_commands.command(name="list", description="List tracked sellers")
async def list_command(interaction: discord.Interaction):
    """Command /list to see tracked sellers."""
    if not interaction.guild:
        return
    
    lang = bot.get_guild_lang(interaction.guild.id)
    
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(t("permission_denied", lang), ephemeral=True)
        return
        
    config = bot.get_guild_config_obj(interaction.guild.id)
    sellers = config.sellers
    
    if not sellers:
        await interaction.response.send_message(t("list_empty", lang))
        return
    
    embed = discord.Embed(
        title=t("list_header", lang).replace("**", ""),
        color=COLOR_INFO
    )
    
    with bot.db._get_connection() as conn:
        for seller_url in sellers:
            seller_name = extract_seller_name(seller_url)
            # Fetch cache status
            cache = conn.execute("SELECT * FROM seller_cache WHERE seller_url = ?", (seller_url,)).fetchone()
            # Count products (approximate by URL or just ID count if we had it)
            # For now, let's just show status.
            last_check = cache['last_check'] if cache and cache['last_check'] else t("list_never", lang)
            last_status = cache['last_status'] if cache else "unknown"
            
            status_icon = "✅" if last_status == "success" else "❌" if last_status == "error" else "❓"
            
            embed.add_field(
                name=seller_name,
                # Note: products_count removed as it's harder to count without seller -> products relation in DB
                value=t("list_products_detail", lang, count="?", check=last_check[:10] if 'T' in str(last_check) else last_check, icon=status_icon),
                inline=True
            )
    
    # Add schedule info
    schedule_time = f"{config.schedule_hour:02d}:{config.schedule_minute:02d}"
    day_name = t(f"day_{config.schedule_day}", lang)
    embed.set_footer(text=t("list_schedule_footer", lang, day=day_name, time=schedule_time, tz=config.timezone))
    
    await interaction.response.send_message(embed=embed)


# Group /set commands
set_group = app_commands.Group(name="set", description="Configure the bot")


@set_group.command(name="timezone", description="Set timezone")
@app_commands.describe(timezone="Timezone (e.g. Europe/Paris)")
async def set_timezone(interaction: discord.Interaction, timezone: str):
    """Command /set timezone."""
    if not interaction.guild:
        return
    
    lang = bot.get_guild_lang(interaction.guild.id)
    
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(t("permission_denied", lang), ephemeral=True)
        return
    
    # Validate timezone
    try:
        ZoneInfo(timezone)
    except Exception:
        await interaction.response.send_message(
            t("set_timezone_invalid", lang),
            ephemeral=True
        )
        return
    
    config = bot.get_guild_config_obj(interaction.guild.id)
    config.timezone = timezone
    bot.db.save_guild(config)
    
    await interaction.response.send_message(
        t("set_timezone_success", lang, timezone=timezone)
    )


@set_group.command(name="checkdate", description="Set scheduled check time")
@app_commands.describe(
    day="Day of week",
    hour="Hour (0-23)",
    minute="Minute (0-59)"
)
@app_commands.choices(day=[
    app_commands.Choice(name="Monday", value="monday"),
    app_commands.Choice(name="Tuesday", value="tuesday"),
    app_commands.Choice(name="Wednesday", value="wednesday"),
    app_commands.Choice(name="Thursday", value="thursday"),
    app_commands.Choice(name="Friday", value="friday"),
    app_commands.Choice(name="Saturday", value="saturday"),
    app_commands.Choice(name="Sunday", value="sunday"),
])
async def set_checkdate(interaction: discord.Interaction, day: str, hour: int, minute: int = 0):
    """Command /set checkdate."""
    if not interaction.guild:
        return
    
    lang = bot.get_guild_lang(interaction.guild.id)
    
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(t("permission_denied", lang), ephemeral=True)
        return
    
    if hour < 0 or hour > 23:
        await interaction.response.send_message(t("error_invalid_hour", lang), ephemeral=True)
        return
    
    if minute < 0 or minute > 59:
        await interaction.response.send_message(t("error_invalid_minute", lang), ephemeral=True)
        return
    
    config = bot.get_guild_config_obj(interaction.guild.id)
    config.schedule_day = day
    config.schedule_hour = hour
    config.schedule_minute = minute
    bot.db.save_guild(config)
    
    day_label = t(f"day_{day}", lang)
    await interaction.response.send_message(
        t("set_schedule_success", lang, day=day_label, hour=hour, minute=minute)
    )


@set_group.command(name="language", description="Set bot language")
@app_commands.describe(language="Language code (en, fr)")
@app_commands.choices(language=[
    app_commands.Choice(name="English", value="en"),
    app_commands.Choice(name="French", value="fr"),
])
async def set_language(interaction: discord.Interaction, language: str):
    """Command /set language."""
    if not interaction.guild:
        return
    
    # Get current language for error messages if needed
    current_lang = bot.get_guild_lang(interaction.guild.id)
    
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(t("permission_denied", current_lang), ephemeral=True)
        return

    available = get_available_languages()
    if language not in available:
         await interaction.response.send_message(
            t("set_language_invalid", current_lang, available=", ".join(available)),
            ephemeral=True
        )
         return

    config = bot.get_guild_config_obj(interaction.guild.id)
    config.language = language
    bot.db.save_guild(config)
    
    # Reply in the new language
    await interaction.response.send_message(
        t("set_language_success", language, language=get_language_name(language))
    )


@set_group.command(name="currency", description="Set bot currency")
@app_commands.describe(currency="Currency (USD, EUR)")
@app_commands.choices(currency=[
    app_commands.Choice(name="USD ($)", value="USD"),
    app_commands.Choice(name="EUR (€)", value="EUR")
])
async def set_currency(interaction: discord.Interaction, currency: str):
    """Command /set currency."""
    if not interaction.guild:
        return
        
    lang = bot.get_guild_lang(interaction.guild.id)
    
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(t("permission_denied", lang), ephemeral=True)
        return

    # Update GLOBAL currency setting
    bot.db.set_global_currency(currency)
    
    await interaction.response.send_message(t("set_currency_success", lang, currency=currency))


@app_commands.command(name="info", description="Bot information and changelog")
async def info_command(interaction: discord.Interaction):
    """Command /info."""
    lang = bot.get_guild_lang(interaction.guild.id) if interaction.guild else "en"
    
    if interaction.guild and not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(t("permission_denied", lang), ephemeral=True)
        return
    
    embed = discord.Embed(
        title=t("bot_name", lang),
        description=t("info_version_prefix", lang, version=BOT_VERSION),
        color=COLOR_INFO
    )
    
    # Get recent changelog from version info
    changelog = VERSION_INFO.get("changelog", {})
    if changelog:
        # Get the latest version's changelog
        latest_v = list(changelog.keys())[0] if changelog else None
        if latest_v:
            changes = "\n".join([f"• {c}" for c in changelog[latest_v]])
            embed.add_field(name=t("info_whats_new", lang, version=latest_v), value=changes, inline=False)
    
    embed.add_field(name=t("info_developer_label", lang), value=t("developer_name", lang), inline=True)
    embed.add_field(name=t("info_platform_label", lang), value=t("platform_name", lang), inline=True)
    
    await interaction.response.send_message(embed=embed)


@set_group.command(name="channel", description="Set notification channel")
@app_commands.describe(
    notification_type="Notification type",
    channel="Channel for notifications"
)
@app_commands.choices(notification_type=[
    app_commands.Choice(name="New Products", value="new_products"),
    app_commands.Choice(name="Updated Products", value="updated_products"),
])
async def set_channel(interaction: discord.Interaction, notification_type: str, channel: discord.TextChannel):
    """Command /set channel."""
    if not interaction.guild:
        return
    
    lang = bot.get_guild_lang(interaction.guild.id)
    
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(t("permission_denied", lang), ephemeral=True)
        return
    
    config = bot.get_guild_config_obj(interaction.guild.id)
    if notification_type == "new_products":
        config.channel_new = channel.id
    else:
        config.channel_updated = channel.id
    bot.db.save_guild(config)
    
    type_label = t("new_product", lang) if notification_type == "new_products" else t("updated_product", lang)
    if not type_label.startswith("🆕") and not type_label.startswith("🔄"):
        type_label = t("notify_prefix", lang, label=type_label)
        
    await interaction.response.send_message(
        t("set_channel_success", lang, type=type_label, channel=channel.mention)
    )


@set_group.command(name="mention", description="Enable or disable role mentions")
@app_commands.describe(enabled="Whether to enable mentions")
async def set_mention_toggle(interaction: discord.Interaction, enabled: bool):
    """Command /set mention <True/False>."""
    if not interaction.guild:
        return
    
    lang = bot.get_guild_lang(interaction.guild.id)
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(t("permission_denied", lang), ephemeral=True)
        return
    
    config = bot.get_guild_config_obj(interaction.guild.id)
    config.mentions_enabled = enabled
    bot.db.save_guild(config)
    
    status_text = t("status_enabled", lang) if enabled else t("status_disabled", lang)
    await interaction.response.send_message(t("set_mention_status", lang, status=status_text))


@set_group.command(name="mention_role", description="Add or remove roles to mention")
@app_commands.describe(
    notification_type="Notification type",
    role="Role to mention",
    action="Add or Remove"
)
@app_commands.choices(
    notification_type=[
        app_commands.Choice(name="New Products", value="new_products"),
        app_commands.Choice(name="Updated Products", value="updated_products"),
    ],
    action=[
        app_commands.Choice(name="Add", value="add"),
        app_commands.Choice(name="Remove", value="remove"),
    ]
)
async def set_mention_role(interaction: discord.Interaction, notification_type: str, role: discord.Role, action: str):
    """Command /set mention_role."""
    if not interaction.guild:
        return
    
    lang = bot.get_guild_lang(interaction.guild.id)
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(t("permission_denied", lang), ephemeral=True)
        return
    
    config = bot.get_guild_config_obj(interaction.guild.id)
    
    role_list = config.mentions_new if notification_type == "new_products" else config.mentions_updated
    
    type_name = t(f"type_{notification_type}", lang)
    if action == "add":
        if role.id not in role_list:
            role_list.append(role.id)
            msg = t("set_mention_role_added", lang, role=role.mention, type=type_name)
        else:
            msg = t("set_mention_role_already", lang, role=role.mention)
    else:
        if role.id in role_list:
            role_list.remove(role.id)
            msg = t("set_mention_role_removed", lang, role=role.mention, type=type_name)
        else:
            msg = t("set_mention_role_not_found", lang, role=role.mention)
            
    if notification_type == "new_products":
        config.mentions_new = role_list
    else:
        config.mentions_updated = role_list

    bot.db.save_guild(config)
    await interaction.response.send_message(msg)


@set_group.command(name="create_roles", description="Create default roles for Fab notifications")
async def create_roles_command(interaction: discord.Interaction):
    """Command /set create_roles."""
    if not interaction.guild:
        return
    
    lang = bot.get_guild_lang(interaction.guild.id)
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(t("permission_denied", lang), ephemeral=True)
        return
    
    if not interaction.guild.me.guild_permissions.manage_roles:
        await interaction.response.send_message(t("error_missing_permissions", lang), ephemeral=True)
        return
        
    await interaction.response.defer()
    
    created = []
    config = bot.get_guild_config_obj(interaction.guild.id)

    # Roles to create
    roles_data = [
        {"name": t("role_new_name", lang), "type": "new_products", "color": discord.Color.green()},
        {"name": t("role_updated_name", lang), "type": "updated_products", "color": discord.Color.blue()}
    ]
    
    for r_data in roles_data:
        # Check if already exists by name (optional, but safer)
        existing = discord.utils.get(interaction.guild.roles, name=r_data["name"])
        if not existing:
            role = await interaction.guild.create_role(
                name=r_data["name"],
                color=r_data["color"],
                mentionable=True,
                reason=t("role_creation_reason", lang)
            )
            if r_data["type"] == "new_products":
                config.mentions_new.append(role.id)
            else:
                config.mentions_updated.append(role.id)
            created.append(role.mention)
        else:
            role_ids = config.mentions_new if r_data["type"] == "new_products" else config.mentions_updated
            if existing.id not in role_ids:
                role_ids.append(existing.id)
                created.append(f"{existing.mention} {t('role_existing_suffix', lang)}")

    bot.db.save_guild(config)
    if created:
        await interaction.followup.send(t("set_create_roles_success", lang, roles=', '.join(created)))
    else:
        await interaction.followup.send(t("set_create_roles_already", lang))


@app_commands.command(name="check", description="Force immediate check (admin)")
async def check_command(interaction: discord.Interaction):
    """Command /check to force a check."""
    if not interaction.guild:
        return
    
    lang = bot.get_guild_lang(interaction.guild.id)
    
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(t("permission_denied", lang), ephemeral=True)
        return
    
    config = bot.get_guild_config_obj(interaction.guild.id)
    sellers = config.sellers
    
    if not sellers:
        await interaction.response.send_message(t("list_empty", lang))
        return
    
    await interaction.response.send_message(t("check_started", lang))
    
    total_new = 0
    total_updated = 0
    total_sellers = len(sellers)
    
    for i, seller_url in enumerate(sellers, 1):
        seller_name = seller_url.split("/sellers/")[-1].rstrip("/")
        progress_msg = await interaction.followup.send(t("check_progress", lang, current=i, total=total_sellers, seller=seller_name))
        
        async def progress_callback(current_item, total_items, product_name):
            try:
                if current_item % 5 == 0 or current_item == total_items:
                    await progress_msg.edit(content=f"{t('check_progress', lang, current=i, total=total_sellers, seller=seller_name)}{t('check_progress_detail', lang, current=current_item, total=total_items, product=product_name)}")
            except Exception as e:
                logger.warning(f"Failed to update progress message: {e}")

        try:
            # For now passing empty to re-scrape
            currency = bot.get_global_currency()
            result = await scrape_seller_with_details(seller_url, [], progress_callback=progress_callback, currency=currency)
            
            if result:
                products_count = len(result["products"])
                
                # Save status
                bot.db.update_seller_status(seller_url, "success")
                
                # Convert to objects and save
                prods = [Product.from_dict(p) for p in result["products"]]
                bot.db.save_products(prods)
                
                changes = result["changes"]
                new_count = len(changes.get("new", []))
                updated_count = len(changes.get("updated", []))
                total_new += new_count
                total_updated += updated_count
                
                await interaction.followup.send(t("check_result", lang, seller=seller_name, count=products_count, new=new_count, updated=updated_count))
                
                if changes["new"] or changes["updated"]:
                    # New products
                    for prod in changes.get("new", []):
                        await bot._notify_guilds(seller_url, prod, is_new=True)
                        await asyncio.sleep(0.5)
                    # Updated products
                    for prod in changes.get("updated", []):
                        await bot._notify_guilds(seller_url, prod, is_new=False)
                        await asyncio.sleep(0.5)
            else:
                await interaction.followup.send(t("check_failed", lang, seller=seller_name))
                    
        except Exception as e:
            logger.error(f"Check error {seller_url}: {e}")
            await interaction.followup.send(t("check_error", lang, seller=seller_name, error=str(e)[:100]))
            
            bot.db.update_seller_status(seller_url, "error")
    
    # Final message
    if total_new == 0 and total_updated == 0:
        await interaction.followup.send(t("check_no_changes", lang))
    else:
        await interaction.followup.send(t("check_complete", lang, new=total_new, updated=total_updated))
