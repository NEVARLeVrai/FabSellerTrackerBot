# -*- coding: utf-8 -*-
"""
Fab Seller Tracker Bot
Discord Bot to track seller products on Fab.com
"""
import json
import os
import asyncio
from datetime import datetime, timedelta
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
from loguru import logger
from zoneinfo import ZoneInfo

from .config import (
    TOKEN,
    DATA_FOLDER,
    SELLERS_FILE,
    PRODUCTS_CACHE_FILE,
    DEFAULT_CHECK_SCHEDULE,
    DEFAULT_TIMEZONE,
    WEEKDAYS,
    COLOR_NEW_PRODUCT,
    COLOR_UPDATED_PRODUCT,
    COLOR_INFO,
    LOG_FILE
)
from .scraper import scrape_seller_with_details
from .lang import t, get_available_languages, get_language_name

logger.add(LOG_FILE, rotation="10 MB", level="INFO")


# ============================================================================
# Utility functions for storage
# ============================================================================

def load_json(filepath: str) -> dict:
    """Loads a JSON file."""
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading {filepath}: {e}")
    return {}


def save_json(filepath: str, data: dict):
    """Saves to a JSON file."""
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info(f"Saved: {filepath}")
    except Exception as e:
        logger.error(f"Error saving {filepath}: {e}")


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
        
        # File paths
        self.data_folder = DATA_FOLDER
        self.sellers_file = os.path.join(self.data_folder, SELLERS_FILE)
        self.products_file = os.path.join(self.data_folder, PRODUCTS_CACHE_FILE)
        
        # Data
        self.subscriptions = {}  # By guild_id
        self.products_cache = {}  # By seller_url
        
        # Scheduler
        self.next_check_time = None
        self.check_task = None
        
    async def setup_hook(self):
        """Called at bot startup."""
        # Load data
        self._load_data()
        
        # Add commands
        self.tree.add_command(sub_command)
        self.tree.add_command(unsub_command)
        self.tree.add_command(list_command)
        self.tree.add_command(set_group)
        self.tree.add_command(check_command)
        
        # Sync commands
        await self.tree.sync()
        logger.info("Slash commands synced")
        
    def _load_data(self):
        """Loads data from files."""
        os.makedirs(self.data_folder, exist_ok=True)
        self.subscriptions = load_json(self.sellers_file)
        self.products_cache = load_json(self.products_file)
        logger.info(f"Loaded: {len(self.subscriptions)} guilds, {len(self.products_cache)} cached sellers")
        
    def _save_data(self):
        """Saves data to files."""
        save_json(self.sellers_file, self.subscriptions)
        save_json(self.products_file, self.products_cache)
        
    def get_guild_config(self, guild_id: int) -> dict:
        """Returns guild config (or creates default)."""
        guild_id_str = str(guild_id)
        if guild_id_str not in self.subscriptions:
            self.subscriptions[guild_id_str] = {
                "sellers": [],
                "timezone": DEFAULT_TIMEZONE,
                "check_schedule": DEFAULT_CHECK_SCHEDULE.copy(),
                "language": "en",  # Default to English
                "channels": {
                    "new_products": None,
                    "updated_products": None,
                    "default": None
                }
            }
        
        # Ensure GLOBAL config exists
        if "GLOBAL" not in self.subscriptions:
            self.subscriptions["GLOBAL"] = {"currency": "USD"}
            
        # Ensure language exists in config (migration)
        if "language" not in self.subscriptions[guild_id_str]:
            self.subscriptions[guild_id_str]["language"] = "en"
            
        return self.subscriptions[guild_id_str]
    
    def get_guild_lang(self, guild_id: int) -> str:
        """Returns configured language for a guild."""
        config = self.get_guild_config(guild_id)
        return config.get("language", "en")
    
    def get_global_currency(self) -> str:
        """Returns the global currency setting."""
        return self.subscriptions.get("GLOBAL", {}).get("currency", "USD")
    
    async def on_ready(self):
        """Called when bot is ready."""
        logger.info(f"Connected as {self.user}")
        
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
        """Calculates next check date."""
        # Get config from first guild with a schedule
        for config in self.subscriptions.values():
            schedule = config.get("check_schedule", DEFAULT_CHECK_SCHEDULE)
            tz = ZoneInfo(config.get("timezone", DEFAULT_TIMEZONE))
            
            now = datetime.now(tz)
            target_weekday = WEEKDAYS.get(schedule.get("day", "sunday"), 6)
            target_hour = schedule.get("hour", 0)
            target_minute = schedule.get("minute", 0)
            
            # Calculate next corresponding day
            days_ahead = target_weekday - now.weekday()
            if days_ahead < 0:
                days_ahead += 7
            elif days_ahead == 0:
                # Same day, check time
                if now.hour > target_hour or (now.hour == target_hour and now.minute >= target_minute):
                    days_ahead = 7
            
            next_check = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
            next_check += timedelta(days=days_ahead)
            
            return next_check
            
        return None
    
    async def _check_all_sellers(self):
        """Checks all sellers from all guilds."""
        logger.info("Starting check for all sellers")
        
        all_sellers = set()
        for config in self.subscriptions.values():
            all_sellers.update(config.get("sellers", []))
        
        for seller_url in all_sellers:
            try:
                existing_products = self.products_cache.get(seller_url, {}).get("products", [])
                
                # Check global currency
                currency = self.get_global_currency()
                result = await scrape_seller_with_details(seller_url, existing_products, currency=currency)
                
                if result:
                    # Update cache
                    self.products_cache[seller_url] = {
                        "last_check": datetime.now().isoformat(),
                        "last_status": "success",
                        "products": result["products"]
                    }
                    
                    # Notify subscribed guilds
                    changes = result["changes"]
                    if changes["new"] or changes["updated"]:
                        await self._notify_guilds(seller_url, changes)
                    
                self._save_data()
                
            except Exception as e:
                logger.error(f"Check error {seller_url}: {e}")
                # Update status to error
                if seller_url in self.products_cache:
                    self.products_cache[seller_url]["last_check"] = datetime.now().isoformat()
                    self.products_cache[seller_url]["last_status"] = "error"
                    self._save_data()
                
        logger.info("Check completed")
        
    async def _notify_guilds(self, seller_url: str, changes: dict):
        """Notifies all guilds subscribed to a seller."""
        seller_name = extract_seller_name(seller_url)
        
        for guild_id_str, config in self.subscriptions.items():
            if seller_url not in config.get("sellers", []):
                continue
                
            try:
                guild = self.get_guild(int(guild_id_str))
                if not guild:
                    continue
                
                lang = self.get_guild_lang(int(guild_id_str))
                channels = config.get("channels", {})
                
                # New products
                for product in changes.get("new", []):
                    channel_id = channels.get("new_products") or channels.get("default")
                    if channel_id:
                        channel = guild.get_channel(channel_id)
                        if channel:
                            embed = self._create_product_embed(product, is_new=True, seller_name=seller_name, seller_url=seller_url, lang=lang)
                            await channel.send(embed=embed)
                            await asyncio.sleep(0.5)
                
                # Updated products
                for product in changes.get("updated", []):
                    channel_id = channels.get("updated_products") or channels.get("default")
                    if channel_id:
                        channel = guild.get_channel(channel_id)
                        if channel:
                            embed = self._create_product_embed(product, is_new=False, seller_name=seller_name, seller_url=seller_url, lang=lang)
                            await channel.send(embed=embed)
                            await asyncio.sleep(0.5)
                            
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
        price_val = product.get("price")
        if not price_val:
             price_val = t("price_not_available", lang)
        else:
            # Localize licenses
            price_val = price_val.replace("Personal", t("license_personal", lang))
            price_val = price_val.replace("Professional", t("license_professional", lang))
             
        embed.add_field(name=t("embed_price", lang), value=price_val, inline=False)
        
        if seller_name:
            val = f"[{seller_name}]({seller_url})" if seller_url else seller_name
            embed.add_field(name=t("embed_seller", lang), value=val, inline=True)
        
        # Last update
        if product.get("last_update"):
            embed.add_field(name=t("embed_last_update", lang), value=product["last_update"], inline=True)
        
        # If updated, show change
        if not is_new:
            if product.get("previous_update"):
                # "Update: {old} -> {new}"
                old_up = product['previous_update']
                new_up = product.get('last_update') or "Now"
                embed.add_field(
                    name=t("embed_change", lang),
                    value=t("change_update_format", lang, old=old_up, new=new_up),
                    inline=False
                )
            elif product.get("previous_price") is not None:
                # "Price: {old} -> {new}"
                old_price = product['previous_price'] or t("price_not_available", lang)
                new_price = product.get('price') or t("price_not_available", lang)
                embed.add_field(
                    name=t("embed_change", lang),
                    value=t("change_price_format", lang, old=old_price, new=new_price),
                    inline=False
                )
        
        # Short description
        if product.get("description"):
            desc = product["description"][:200]
            if len(product["description"]) > 200:
                desc += "..."
            embed.add_field(name=t("embed_description", lang), value=desc, inline=False)

        # Changelog
        changelog = product.get("changelog")
        if changelog:
            # It's a list of dates usually
            val = "\n".join(changelog[:5])
        else:
            val = t("none", lang)
        
        embed.add_field(name=t("embed_changelog", lang), value=val, inline=False)
        
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
        await interaction.response.send_message(t("error_only_in_guild", "en"))
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
    config = bot.get_guild_config(interaction.guild.id)
    
    if normalized_url in config["sellers"]:
        await interaction.response.send_message(t("sub_already", lang), ephemeral=True)
        return
    
    config["sellers"].append(normalized_url)
    
    # Set default channel if not configured
    if config["channels"]["default"] is None:
        config["channels"]["default"] = interaction.channel.id
    
    bot._save_data()
    
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
    config = bot.get_guild_config(interaction.guild.id)
    
    if normalized_url not in config["sellers"]:
        await interaction.response.send_message(t("unsub_not_found", lang), ephemeral=True)
        return
    
    config["sellers"].remove(normalized_url)
    bot._save_data()
    
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
    config = bot.get_guild_config(interaction.guild.id)
    sellers = config.get("sellers", [])
    
    if not sellers:
        await interaction.response.send_message(t("list_empty", lang))
        return
    
    embed = discord.Embed(
        title=t("list_header", lang).replace("**", ""),
        color=COLOR_INFO
    )
    
    for seller_url in sellers:
        seller_name = extract_seller_name(seller_url)
        cache = bot.products_cache.get(seller_url, {})
        products_count = len(cache.get("products", []))
        last_check = cache.get("last_check", "Never")
        last_status = cache.get("last_status", "unknown")
        
        status_icon = "✅" if last_status == "success" else "❌" if last_status == "error" else "❓"
        
        embed.add_field(
            name=seller_name,
            value=f"Products: {products_count}\nCheck: {last_check[:10] if 'T' in str(last_check) else last_check} {status_icon}",
            inline=True
        )
    
    # Add schedule info
    schedule = config.get("check_schedule", DEFAULT_CHECK_SCHEDULE)
    tz = config.get("timezone", DEFAULT_TIMEZONE)
    embed.set_footer(text=f"Schedule: {schedule.get('day')} {schedule.get('hour'):02d}:{schedule.get('minute'):02d} ({tz})")
    
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
    
    config = bot.get_guild_config(interaction.guild.id)
    config["timezone"] = timezone
    bot._save_data()
    
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
    
    config = bot.get_guild_config(interaction.guild.id)
    config["check_schedule"] = {
        "day": day,
        "hour": hour,
        "minute": minute
    }
    bot._save_data()
    
    await interaction.response.send_message(
        t("set_schedule_success", lang, day=day, hour=hour, minute=minute)
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

    config = bot.get_guild_config(interaction.guild.id)
    config["language"] = language
    bot._save_data()
    
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

    # Update GLOBAL config
    if "GLOBAL" not in bot.subscriptions:
        bot.subscriptions["GLOBAL"] = {}
    
    bot.subscriptions["GLOBAL"]["currency"] = currency
    bot._save_data()
    
    await interaction.response.send_message(t("set_currency_success", lang, currency=currency))


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
    
    config = bot.get_guild_config(interaction.guild.id)
    config["channels"][notification_type] = channel.id
    bot._save_data()
    
    type_label = t("new_product", lang) if notification_type == "new_products" else t("updated_product", lang)
    if not type_label.startswith("🆕") and not type_label.startswith("🔄"):
        type_label = notification_type # Fallback
        
    await interaction.response.send_message(
        t("set_channel_success", lang, type=type_label, channel=channel.mention)
    )


@app_commands.command(name="check", description="Force immediate check (admin)")
async def check_command(interaction: discord.Interaction):
    """Command /check to force a check."""
    if not interaction.guild:
        return
    
    lang = bot.get_guild_lang(interaction.guild.id)
    
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(t("permission_denied", lang), ephemeral=True)
        return
    
    config = bot.get_guild_config(interaction.guild.id)
    sellers = config.get("sellers", [])
    
    if not sellers:
        await interaction.response.send_message(t("list_empty", lang))
        return
    
    await interaction.response.send_message(t("check_started", lang))
    
    total_new = 0
    total_updated = 0
    total_sellers = len(sellers)
    
    for i, seller_url in enumerate(sellers, 1):
        seller_name = seller_url.split("/sellers/")[-1].rstrip("/")
        
        # Send progress message
        progress_msg = await interaction.followup.send(t("check_progress", lang, current=i, total=total_sellers, seller=seller_name))
        
        async def progress_callback(current_item, total_items, product_name):
            try:
                # Update message every 5 items or if it's the last one to avoid rate limits
                if current_item % 5 == 0 or current_item == total_items:
                    await progress_msg.edit(content=f"{t('check_progress', lang, current=i, total=total_sellers, seller=seller_name)}\nItem {current_item}/{total_items}: {product_name}")
            except Exception as e:
                logger.warning(f"Failed to update progress message: {e}")

        try:
            existing_products = bot.products_cache.get(seller_url, {}).get("products", [])
            currency = bot.get_global_currency()
            result = await scrape_seller_with_details(seller_url, existing_products, progress_callback=progress_callback, currency=currency)
            
            if result:
                products_count = len(result["products"])
                bot.products_cache[seller_url] = {
                    "last_check": datetime.now().isoformat(),
                    "last_status": "success",
                    "products": result["products"]
                }
                
                changes = result["changes"]
                new_count = len(changes.get("new", []))
                updated_count = len(changes.get("updated", []))
                total_new += new_count
                total_updated += updated_count
                
                # Result message for this seller
                await interaction.followup.send(
                    t("check_result", lang, seller=seller_name, count=products_count, new=new_count, updated=updated_count)
                )
                
                # Notify
                if changes["new"] or changes["updated"]:
                    await bot._notify_guilds(seller_url, changes)
            else:
                await interaction.followup.send(t("check_failed", lang, seller=seller_name))
                    
        except Exception as e:
            logger.error(f"Check error {seller_url}: {e}")
            await interaction.followup.send(t("check_error", lang, seller=seller_name, error=str(e)[:100]))
            
            # Update status to error
            if seller_url in bot.products_cache:
                bot.products_cache[seller_url]["last_check"] = datetime.now().isoformat()
                bot.products_cache[seller_url]["last_status"] = "error"
    
    bot._save_data()
    
    # Final message
    if total_new == 0 and total_updated == 0:
        await interaction.followup.send(t("check_no_changes", lang))
    else:
        await interaction.followup.send(
            t("check_complete", lang, new=total_new, updated=total_updated)
        )
