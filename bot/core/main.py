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
    # Handle /sellers/ or /Sellers/
    url_lower = url.lower()
    if "/sellers/" in url_lower:
        parts = url.lower().split("/sellers/")
        if len(parts) > 1:
            return parts[1].rstrip("/").split("?")[0].lower()
    return None


def normalize_seller_url(url: str) -> Optional[str]:
    """Normalizes the seller URL."""
    name = extract_seller_name(url)
    if name:
        return f"https://fab.com/sellers/{name}"
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
        self.is_syncing = False
        
    async def setup_hook(self):
        """Called at bot startup."""
        # Database initialized in __init__
        
        # Add commands
        self.tree.add_command(sub_command)
        self.tree.add_command(unsub_command)
        self.tree.add_command(list_command)
        self.tree.add_command(set_group)
        self.tree.add_command(info_command)
        self.tree.add_command(check_group)
        
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
            
    def restart_scheduler(self):
        """Cancels and restarts the scheduler loop (useful when config changes)."""
        if self.check_task:
            self.check_task.cancel()
            logger.info("Scheduler task cancelled for restart")
        
        self.check_task = self.loop.create_task(self._schedule_loop())
        logger.info("Scheduler task restarted")

    async def _schedule_loop(self):
        """Main scheduler loop."""
        while True:
            try:
                # Calculate next check
                next_check = self._calculate_next_check()
                if next_check:
                    self.next_check_time = next_check
                    now = datetime.now(next_check.tzinfo)
                    wait_seconds = (next_check - now).total_seconds()
                    
                    if wait_seconds > 0:
                        logger.info(f"┌───────────────────────────────────────────────────┐")
                        logger.info(f"│ 🕒 NEXT SYNC IN: {wait_seconds/3600:.1f} hours ({next_check.strftime('%A %H:%M')})")
                        logger.info(f"└───────────────────────────────────────────────────┘")
                        await asyncio.sleep(wait_seconds)
                    
                    # Execute check
                    await self._check_all_sellers()
                else:
                    # No scheduled check, wait 1 hour and try again
                    logger.debug("No active schedules found, sleeping 1 hour")
                    await asyncio.sleep(3600)
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Scheduler error: {e}")
                await asyncio.sleep(60)
                
    def _calculate_next_check(self) -> Optional[datetime]:
        """Calculates next check date based on all configured schedules and frequencies."""
        guilds = self.db.get_all_guilds()
        
        if not guilds:
            return None
            
        next_checks = []
        for config in guilds:
            tz = ZoneInfo(config.timezone or DEFAULT_TIMEZONE)
            now = datetime.now(tz)
            
            freq = config.schedule_frequency or "weekly"
            target_hour = config.schedule_hour or 0
            target_minute = config.schedule_minute or 0
            
            if freq == "daily":
                check_dt = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
                if check_dt <= now:
                    check_dt += timedelta(days=1)
                next_checks.append(check_dt)
                
            elif freq == "monthly":
                try:
                    # day_val should be 1-28 for safety (all months have 28 days)
                    day_num = int(config.schedule_day)
                except (ValueError, TypeError):
                    day_num = 1
                
                # Try this month
                try:
                    check_dt = now.replace(day=day_num, hour=target_hour, minute=target_minute, second=0, microsecond=0)
                except ValueError:
                    # If day_num is 31 and month has 30, fallback to last day or next month
                    check_dt = now.replace(day=28, hour=target_hour, minute=target_minute, second=0, microsecond=0)
                
                if check_dt <= now:
                    # Move to next month
                    next_month = now.month + 1
                    next_year = now.year
                    if next_month > 12:
                        next_month = 1
                        next_year += 1
                    try:
                        check_dt = check_dt.replace(year=next_year, month=next_month, day=day_num)
                    except ValueError:
                        check_dt = check_dt.replace(year=next_year, month=next_month, day=28)
                
                next_checks.append(check_dt)
                
            else: # weekly
                target_weekday = WEEKDAYS.get(config.schedule_day or "sunday", 6)
                
                days_ahead = target_weekday - now.weekday()
                if days_ahead < 0:
                    days_ahead += 7
                elif days_ahead == 0:
                    if now.hour > target_hour or (now.hour == target_hour and now.minute >= target_minute):
                        days_ahead = 7
                
                check_dt = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
                check_dt += timedelta(days=days_ahead)
                next_checks.append(check_dt)
            
        if not next_checks:
            return None
            
        # Return the earliest check time
        return min(next_checks)
    
    async def _check_all_sellers(self):
        """Checks all sellers from all guilds."""
        if self.is_syncing:
            logger.warning("Automated sync skipped: Sync already in progress")
            return
            
        self.is_syncing = True
        try:
            # Get all unique sellers from all guilds
            with self.db._get_connection() as conn:
                rows = conn.execute("SELECT DISTINCT seller_url FROM subscriptions").fetchall()
                all_sellers = [r['seller_url'] for r in rows]
            
            count_total = len(all_sellers)
            logger.info(f"┌───────────────────────────────────────────────────┐")
            logger.info(f"│ 🔄 SYNC STARTED ({count_total} sellers to check)        │")
            logger.info(f"└───────────────────────────────────────────────────┘")
            
            success_count = 0
            error_count = 0
            
            for i, seller_url in enumerate(all_sellers, 1):
                try:
                    seller_name = extract_seller_name(seller_url)
                    logger.info(f"  » Syncing [{i}/{count_total}]: {seller_name}")
                    
                    currency = self.get_global_currency()
                    existing_products = self.db.get_seller_products(seller_url)
                    
                    result = await scrape_seller_with_details(seller_url, existing_products, currency=currency)
                    
                    if result:
                        products_count = len(result["products"])
                        self.db.update_seller_status(seller_url, "success", product_count=products_count)
                        self.db.save_products(result["products"], seller_url=seller_url)
                        
                        changes = result["changes"]
                        new_c = len(changes.get("new", []))
                        upd_c = len(changes.get("updated", []))
                        if new_c > 0 or upd_c > 0:
                            logger.info(f"  ↳ Changes: {new_c} new, {upd_c} updated")
                        
                        for prod in changes.get("new", []):
                            await self._notify_guilds(seller_url, prod, is_new=True)
                            await asyncio.sleep(0.5)
                            
                        for prod in changes.get("updated", []):
                            await self._notify_guilds(seller_url, prod, is_new=False)
                            await asyncio.sleep(0.5)
                        
                        success_count += 1
                    else:
                        logger.warning(f"  ↳ Scraping failed for {seller_name}")
                        error_count += 1
                    
                except Exception as e:
                    logger.error(f"  ↳ Check error for {seller_url}: {e}")
                    self.db.update_seller_status(seller_url, "error")
                    error_count += 1
                    
            logger.info(f"┌───────────────────────────────────────────────────┐")
            logger.info(f"│ ✅ SYNC COMPLETED: {success_count} success, {error_count} errors      │")
            logger.info(f"└───────────────────────────────────────────────────┘")
        
        finally:
            self.is_syncing = False
            
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
    bot.db.save_guild(config)
    
    seller_name = extract_seller_name(normalized_url)
    msg = t("sub_success", lang, seller=seller_name)
    
    # Validation: warn if no channels are set
    if config.channel_new is None or config.channel_updated is None:
        msg += f"\n\n{t('sub_no_channel_tip', lang)}"
    
    await interaction.response.send_message(msg)


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
            last_check = cache['last_check'] if cache and cache['last_check'] else t("list_never", lang)
            last_status = cache['last_status'] if cache else "unknown"
            product_count = cache['product_count'] if cache and cache['product_count'] else 0
            
            status_icon = "✅" if last_status == "success" else "❌" if last_status == "error" else "❓"
            
            embed.add_field(
                name=seller_name,
                value=t("list_products_detail", lang, count=product_count, check=last_check[:10] if 'T' in str(last_check) else last_check, icon=status_icon),
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
    bot.restart_scheduler()


@set_group.command(name="checkdate", description="Set scheduled check time and frequency")
@app_commands.describe(
    frequency="Frequency of checks",
    day_val="Day value (Weekday name for weekly, Day number 1-28 for monthly, ignore for daily)",
    hour="Hour (0-23)",
    minute="Minute (0-59)"
)
@app_commands.choices(frequency=[
    app_commands.Choice(name="Daily", value="daily"),
    app_commands.Choice(name="Weekly", value="weekly"),
    app_commands.Choice(name="Monthly", value="monthly"),
])
async def set_checkdate(interaction: discord.Interaction, frequency: str, day_val: str, hour: int, minute: int = 0):
    """Command /set checkdate."""
    lang = bot.get_guild_lang(interaction.guild.id)
    
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(t("permission_denied", lang), ephemeral=True)
        return
        
    # Validate frequency and day_val
    day_cleaned = day_val.lower()
    if frequency == "weekly":
        if day_cleaned not in WEEKDAYS:
            await interaction.response.send_message(t("error_invalid_weekday", lang), ephemeral=True)
            return
    elif frequency == "monthly":
        try:
            day_num = int(day_val)
            if day_num < 1 or day_num > 28:
                await interaction.response.send_message(t("error_invalid_day_num", lang), ephemeral=True)
                return
        except ValueError:
            await interaction.response.send_message(t("error_invalid_day_num", lang), ephemeral=True)
            return
            
    config = bot.get_guild_config_obj(interaction.guild.id)
    config.schedule_frequency = frequency
    config.schedule_day = day_cleaned if frequency != "daily" else "everyday"
    config.schedule_hour = hour
    config.schedule_minute = minute
    bot.db.save_guild(config)
    
    freq_label = t(f"freq_{frequency}", lang)
    if frequency == "weekly":
        day_label = t(f"day_{day_cleaned}", lang)
        msg = t("set_schedule_success_weekly", lang, freq=freq_label, day=day_label, hour=hour, minute=minute)
    elif frequency == "monthly":
        msg = t("set_schedule_success_monthly", lang, freq=freq_label, day=day_val, hour=hour, minute=minute)
    else: # daily
        msg = t("set_schedule_success_daily", lang, freq=freq_label, hour=hour, minute=minute)

    await interaction.response.send_message(msg)
    bot.restart_scheduler()


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


# Group /check commands
check_group = app_commands.Group(name="check", description="Verification commands")

@check_group.command(name="now", description="Force an immediate check for all sellers")
async def check_now(interaction: discord.Interaction):
    """Command /check now to force an immediate check."""
    if not interaction.guild:
        await interaction.response.send_message(t("error_only_in_guild"))
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
    
    # Validation: early exit if no channels are configured
    if config.channel_new is None and config.channel_updated is None:
        await interaction.followup.send(f"❌ {t('check_no_channel_warn', lang)}\n\n{t('sub_no_channel_tip', lang)}")
        return
        
    # Validation: early exit if already syncing
    if bot.is_syncing:
        await interaction.followup.send(f"❌ {t('sync_already_in_progress', lang)}")
        return
        
    bot.is_syncing = True
    try:
        logger.info(f"┌───────────────────────────────────────────────────┐")
        logger.info(f"│ 🔄 MANUAL SYNC STARTED (Guild: {interaction.guild.name})")
        logger.info(f"└───────────────────────────────────────────────────┘")
    
        total_new = 0
        total_updated = 0
        total_sellers = len(sellers)
        success_count = 0
        error_count = 0
        
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
                logger.info(f"  » Syncing [{i}/{total_sellers}]: {seller_name}")
                
                currency = bot.get_global_currency()
                existing_products = bot.db.get_seller_products(seller_url)
                
                result = await scrape_seller_with_details(seller_url, existing_products, progress_callback=progress_callback, currency=currency)
                
                if result:
                    products_count = len(result["products"])
                    
                    # Save status
                    bot.db.update_seller_status(seller_url, "success", product_count=products_count)
                    
                    # Convert to objects and save
                    prods = result["products"]
                    bot.db.save_products(prods, seller_url=seller_url)
                    
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
                    success_count += 1
                else:
                    await interaction.followup.send(t("check_failed", lang, seller=seller_name))
                    error_count += 1
                        
            except Exception as e:
                logger.error(f"Manual check error {seller_url}: {e}")
                await interaction.followup.send(t("check_error", lang, seller=seller_name, error=str(e)[:100]))
                
                bot.db.update_seller_status(seller_url, "error")
                error_count += 1
        
        logger.info(f"┌───────────────────────────────────────────────────┐")
        logger.info(f"│ ✅ MANUAL SYNC COMPLETED: {success_count} success, {error_count} errors")
        logger.info(f"└───────────────────────────────────────────────────┘")
    
        # Final message
        if total_new == 0 and total_updated == 0:
            await interaction.followup.send(t("check_no_changes", lang))
        else:
            await interaction.followup.send(t("check_complete", lang, new=total_new, updated=total_updated))
            
    finally:
        bot.is_syncing = False


@check_group.command(name="config", description="View server configuration and settings")
async def check_config(interaction: discord.Interaction):
    """Command /check config to see DB settings."""
    if not interaction.guild:
        await interaction.response.send_message(t("error_only_in_guild"))
        return
    
    lang = bot.get_guild_lang(interaction.guild.id)
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(t("permission_denied", lang), ephemeral=True)
        return
        
    config = bot.get_guild_config_obj(interaction.guild.id)
    
    embed = discord.Embed(
        title=t("config_title", lang),
        color=COLOR_INFO,
        timestamp=datetime.now()
    )
    
    # General Settings
    gen_val = (
        f"**{t('config_timezone', lang)}**: {config.timezone}\n"
        f"**{t('config_language', lang)}**: {get_language_name(config.language)} ({config.language})\n"
        f"**{t('config_currency', lang)}**: {config.currency}"
    )
    embed.add_field(name=f"📋 {t('config_general', lang)}", value=gen_val, inline=False)
    
    # Notifications
    def get_ch_mention(cid):
        return f"<#{cid}>" if cid else f"*{t('config_not_set', lang)}*"
        
    notif_val = (
        f"**{t('config_channel_new', lang)}**: {get_ch_mention(config.channel_new)}\n"
        f"**{t('config_channel_updated', lang)}**: {get_ch_mention(config.channel_updated)}\n"
        f"**{t('config_mentions', lang)}**: {'✅' if config.mentions_enabled else '❌'}\n"
    )
    
    # Roles detail
    roles_new = [f"<@&{rid}>" for rid in config.mentions_new]
    roles_upd = [f"<@&{rid}>" for rid in config.mentions_updated]
    
    notif_val += f"↳ **{t('config_roles_new', lang)}**: {', '.join(roles_new) if roles_new else t('none', lang)}\n"
    notif_val += f"↳ **{t('config_roles_upd', lang)}**: {', '.join(roles_upd) if roles_upd else t('none', lang)}"
    
    embed.add_field(name=f"🔔 {t('config_notifications', lang)}", value=notif_val, inline=False)
    
    # Schedule
    time_str = f"{config.schedule_hour:02d}:{config.schedule_minute:02d}"
    freq = config.schedule_frequency.capitalize() if config.schedule_frequency else "Weekly"
    if config.schedule_frequency == "daily":
        sched_val = f"{freq} @ {time_str} ({config.timezone})"
    elif config.schedule_frequency == "monthly":
        sched_val = f"{freq} ({config.schedule_day}) @ {time_str} ({config.timezone})"
    else:  # weekly
        day_name = t(f"day_{config.schedule_day}", lang)
        sched_val = f"{freq} ({day_name}) @ {time_str} ({config.timezone})"
    embed.add_field(name=f"🕒 {t('config_schedule', lang)}", value=sched_val, inline=True)
    
    # Sellers
    seller_names = [url.split("/sellers/")[-1].rstrip("/") for url in config.sellers]
    sellers_val = f"**{t('config_count', lang, count=len(config.sellers))}**\n"
    if seller_names:
        sellers_val += f"↳ {', '.join(seller_names)}"
    
    embed.add_field(name=f"🏪 {t('config_seller_list', lang)}", value=sellers_val, inline=False)
    
    embed.set_footer(text=f"Server ID: {interaction.guild.id}")
    await interaction.response.send_message(embed=embed)
