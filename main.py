# -*- coding: utf-8 -*-
"""
Fab Seller Tracker Bot
Bot Discord pour suivre les produits de sellers sur Fab.com
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

from config import (
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
    MESSAGES,
    LOG_FILE
)
from scraper import scrape_seller_with_details

logger.add(LOG_FILE, rotation="10 MB", level="INFO")


# ============================================================================
# Fonctions utilitaires pour le stockage
# ============================================================================

def load_json(filepath: str) -> dict:
    """Charge un fichier JSON."""
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Erreur chargement {filepath}: {e}")
    return {}


def save_json(filepath: str, data: dict):
    """Sauvegarde dans un fichier JSON."""
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info(f"Sauvegardé: {filepath}")
    except Exception as e:
        logger.error(f"Erreur sauvegarde {filepath}: {e}")


def extract_seller_name(url: str) -> Optional[str]:
    """Extrait le nom du seller depuis l'URL."""
    # https://www.fab.com/sellers/GameAssetFactory -> GameAssetFactory
    if "/sellers/" in url:
        parts = url.split("/sellers/")
        if len(parts) > 1:
            return parts[1].rstrip("/").split("?")[0]
    return None


def normalize_seller_url(url: str) -> Optional[str]:
    """Normalise l'URL du seller."""
    name = extract_seller_name(url)
    if name:
        return f"https://www.fab.com/sellers/{name}"
    return None


# ============================================================================
# Bot principal
# ============================================================================

class FabSellerTrackerBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
        
        # Chemins des fichiers
        self.data_folder = DATA_FOLDER
        self.sellers_file = os.path.join(self.data_folder, SELLERS_FILE)
        self.products_file = os.path.join(self.data_folder, PRODUCTS_CACHE_FILE)
        
        # Données
        self.subscriptions = {}  # Par guild_id
        self.products_cache = {}  # Par seller_url
        
        # Scheduler
        self.next_check_time = None
        self.check_task = None
        
    async def setup_hook(self):
        """Appelé au démarrage du bot."""
        # Charger les données
        self._load_data()
        
        # Ajouter les commandes
        self.tree.add_command(sub_command)
        self.tree.add_command(unsub_command)
        self.tree.add_command(list_command)
        self.tree.add_command(set_group)
        self.tree.add_command(check_command)
        
        # Synchroniser les commandes
        await self.tree.sync()
        logger.info("Commandes slash synchronisées")
        
    def _load_data(self):
        """Charge les données depuis les fichiers."""
        os.makedirs(self.data_folder, exist_ok=True)
        self.subscriptions = load_json(self.sellers_file)
        self.products_cache = load_json(self.products_file)
        logger.info(f"Chargé: {len(self.subscriptions)} guilds, {len(self.products_cache)} sellers en cache")
        
    def _save_data(self):
        """Sauvegarde les données."""
        save_json(self.sellers_file, self.subscriptions)
        save_json(self.products_file, self.products_cache)
        
    def get_guild_config(self, guild_id: int) -> dict:
        """Retourne la config d'un guild (ou crée une config par défaut)."""
        guild_id_str = str(guild_id)
        if guild_id_str not in self.subscriptions:
            self.subscriptions[guild_id_str] = {
                "sellers": [],
                "timezone": DEFAULT_TIMEZONE,
                "check_schedule": DEFAULT_CHECK_SCHEDULE.copy(),
                "channels": {
                    "new_products": None,
                    "updated_products": None,
                    "default": None
                }
            }
        return self.subscriptions[guild_id_str]
    
    async def on_ready(self):
        """Appelé quand le bot est prêt."""
        logger.info(f"Connecté en tant que {self.user}")
        
        # Démarrer le scheduler
        if self.check_task is None:
            self.check_task = self.loop.create_task(self._schedule_loop())
            
    async def _schedule_loop(self):
        """Boucle principale du scheduler."""
        while True:
            try:
                # Calculer le prochain check
                next_check = self._calculate_next_check()
                if next_check:
                    self.next_check_time = next_check
                    wait_seconds = (next_check - datetime.now(ZoneInfo(DEFAULT_TIMEZONE))).total_seconds()
                    
                    if wait_seconds > 0:
                        logger.info(f"Prochain check dans {wait_seconds/3600:.1f} heures")
                        await asyncio.sleep(wait_seconds)
                    
                    # Exécuter le check
                    await self._check_all_sellers()
                else:
                    # Pas de check configuré, attendre 1 heure
                    await asyncio.sleep(3600)
                    
            except Exception as e:
                logger.error(f"Erreur scheduler: {e}")
                await asyncio.sleep(60)
                
    def _calculate_next_check(self) -> Optional[datetime]:
        """Calcule la date du prochain check."""
        # Prendre la config du premier guild avec un schedule
        for config in self.subscriptions.values():
            schedule = config.get("check_schedule", DEFAULT_CHECK_SCHEDULE)
            tz = ZoneInfo(config.get("timezone", DEFAULT_TIMEZONE))
            
            now = datetime.now(tz)
            target_weekday = WEEKDAYS.get(schedule.get("day", "sunday"), 6)
            target_hour = schedule.get("hour", 0)
            target_minute = schedule.get("minute", 0)
            
            # Calculer le prochain jour correspondant
            days_ahead = target_weekday - now.weekday()
            if days_ahead < 0:
                days_ahead += 7
            elif days_ahead == 0:
                # Même jour, vérifier l'heure
                if now.hour > target_hour or (now.hour == target_hour and now.minute >= target_minute):
                    days_ahead = 7
            
            next_check = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
            next_check += timedelta(days=days_ahead)
            
            return next_check
            
        return None
    
    async def _check_all_sellers(self):
        """Vérifie tous les sellers de tous les guilds."""
        logger.info("Début de la vérification de tous les sellers")
        
        all_sellers = set()
        for config in self.subscriptions.values():
            all_sellers.update(config.get("sellers", []))
        
        for seller_url in all_sellers:
            try:
                existing_products = self.products_cache.get(seller_url, {}).get("products", [])
                
                result = await scrape_seller_with_details(seller_url, existing_products)
                
                if result:
                    # Mettre à jour le cache
                    self.products_cache[seller_url] = {
                        "last_check": datetime.now().isoformat(),
                        "products": result["products"]
                    }
                    
                    # Notifier les guilds abonnés
                    changes = result["changes"]
                    if changes["new"] or changes["updated"]:
                        await self._notify_guilds(seller_url, changes)
                    
                self._save_data()
                
            except Exception as e:
                logger.error(f"Erreur vérification {seller_url}: {e}")
                
        logger.info("Vérification terminée")
        
    async def _notify_guilds(self, seller_url: str, changes: dict):
        """Notifie tous les guilds abonnés à un seller."""
        seller_name = extract_seller_name(seller_url)
        
        for guild_id_str, config in self.subscriptions.items():
            if seller_url not in config.get("sellers", []):
                continue
                
            try:
                guild = self.get_guild(int(guild_id_str))
                if not guild:
                    continue
                
                channels = config.get("channels", {})
                
                # Nouveaux produits
                for product in changes.get("new", []):
                    channel_id = channels.get("new_products") or channels.get("default")
                    if channel_id:
                        channel = guild.get_channel(channel_id)
                        if channel:
                            embed = self._create_product_embed(product, is_new=True, seller_name=seller_name)
                            await channel.send(embed=embed)
                            await asyncio.sleep(0.5)
                
                # Produits mis à jour
                for product in changes.get("updated", []):
                    channel_id = channels.get("updated_products") or channels.get("default")
                    if channel_id:
                        channel = guild.get_channel(channel_id)
                        if channel:
                            embed = self._create_product_embed(product, is_new=False, seller_name=seller_name)
                            await channel.send(embed=embed)
                            await asyncio.sleep(0.5)
                            
            except Exception as e:
                logger.error(f"Erreur notification guild {guild_id_str}: {e}")
    
    def _create_product_embed(self, product: dict, is_new: bool, seller_name: str = None) -> discord.Embed:
        """Crée un embed Discord pour un produit."""
        title = MESSAGES["new_product"] if is_new else MESSAGES["updated_product"]
        color = COLOR_NEW_PRODUCT if is_new else COLOR_UPDATED_PRODUCT
        
        embed = discord.Embed(
            title=f"{title}: {product['name']}",
            url=product.get("url"),
            color=color,
            timestamp=datetime.now()
        )
        
        # Prix
        embed.add_field(name="💰 Prix", value=product.get("price", "N/A"), inline=True)
        
        # Seller
        if seller_name:
            embed.add_field(name="🏪 Seller", value=seller_name, inline=True)
        
        # Last update
        if product.get("last_update"):
            embed.add_field(name="📅 Dernière MAJ", value=product["last_update"], inline=True)
        
        # Si c'est une mise à jour, montrer le changement
        if not is_new:
            if product.get("previous_update"):
                embed.add_field(
                    name="📝 Changement",
                    value=f"MAJ: {product['previous_update']} → {product.get('last_update', 'Maintenant')}",
                    inline=False
                )
            elif product.get("previous_price"):
                embed.add_field(
                    name="📝 Changement",
                    value=f"Prix: {product['previous_price']} → {product.get('price')}",
                    inline=False
                )
        
        # Description courte
        if product.get("description"):
            desc = product["description"][:200]
            if len(product["description"]) > 200:
                desc += "..."
            embed.add_field(name="📄 Description", value=desc, inline=False)
        
        # Image
        if product.get("image"):
            embed.set_thumbnail(url=product["image"])
        
        # Footer
        embed.set_footer(text="Fab Seller Tracker")
        
        return embed


# ============================================================================
# Slash Commands
# ============================================================================

bot = FabSellerTrackerBot()


@app_commands.command(name="sub", description="S'abonner aux produits d'un seller Fab.com")
@app_commands.describe(seller_url="URL du seller (ex: https://fab.com/sellers/GameAssetFactory)")
async def sub_command(interaction: discord.Interaction, seller_url: str):
    """Commande /sub pour s'abonner à un seller."""
    if not interaction.guild:
        await interaction.response.send_message("❌ Cette commande ne peut être utilisée que dans un serveur.")
        return
    
    # Vérifier les permissions
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(MESSAGES["permission_denied"], ephemeral=True)
        return
    
    # Normaliser l'URL
    normalized_url = normalize_seller_url(seller_url)
    if not normalized_url:
        await interaction.response.send_message(MESSAGES["sub_invalid_url"], ephemeral=True)
        return
    
    # Ajouter le seller
    config = bot.get_guild_config(interaction.guild.id)
    
    if normalized_url in config["sellers"]:
        await interaction.response.send_message(MESSAGES["sub_already"], ephemeral=True)
        return
    
    config["sellers"].append(normalized_url)
    
    # Définir le canal par défaut si pas encore configuré
    if config["channels"]["default"] is None:
        config["channels"]["default"] = interaction.channel.id
    
    bot._save_data()
    
    seller_name = extract_seller_name(normalized_url)
    await interaction.response.send_message(
        MESSAGES["sub_success"].format(seller=seller_name)
    )


@app_commands.command(name="unsub", description="Se désabonner d'un seller Fab.com")
@app_commands.describe(seller_url="URL du seller à retirer")
async def unsub_command(interaction: discord.Interaction, seller_url: str):
    """Commande /unsub pour se désabonner."""
    if not interaction.guild:
        await interaction.response.send_message("❌ Cette commande ne peut être utilisée que dans un serveur.")
        return
    
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(MESSAGES["permission_denied"], ephemeral=True)
        return
    
    normalized_url = normalize_seller_url(seller_url)
    config = bot.get_guild_config(interaction.guild.id)
    
    if normalized_url not in config["sellers"]:
        await interaction.response.send_message(MESSAGES["unsub_not_found"], ephemeral=True)
        return
    
    config["sellers"].remove(normalized_url)
    bot._save_data()
    
    seller_name = extract_seller_name(normalized_url)
    await interaction.response.send_message(
        MESSAGES["unsub_success"].format(seller=seller_name)
    )


@app_commands.command(name="list", description="Lister les sellers suivis")
async def list_command(interaction: discord.Interaction):
    """Commande /list pour voir les sellers suivis."""
    if not interaction.guild:
        await interaction.response.send_message("❌ Cette commande ne peut être utilisée que dans un serveur.")
        return
    
    config = bot.get_guild_config(interaction.guild.id)
    sellers = config.get("sellers", [])
    
    if not sellers:
        await interaction.response.send_message(MESSAGES["list_empty"])
        return
    
    embed = discord.Embed(
        title="📋 Sellers suivis",
        color=COLOR_INFO
    )
    
    for seller_url in sellers:
        seller_name = extract_seller_name(seller_url)
        cache = bot.products_cache.get(seller_url, {})
        products_count = len(cache.get("products", []))
        last_check = cache.get("last_check", "Jamais")
        
        embed.add_field(
            name=seller_name,
            value=f"Produits: {products_count}\nDernier check: {last_check[:10] if last_check != 'Jamais' else last_check}",
            inline=True
        )
    
    # Ajouter infos du schedule
    schedule = config.get("check_schedule", DEFAULT_CHECK_SCHEDULE)
    tz = config.get("timezone", DEFAULT_TIMEZONE)
    embed.set_footer(text=f"Vérification: {schedule.get('day')} à {schedule.get('hour'):02d}:{schedule.get('minute'):02d} ({tz})")
    
    await interaction.response.send_message(embed=embed)


# Groupe de commandes /set
set_group = app_commands.Group(name="set", description="Configurer le bot")


@set_group.command(name="timezone", description="Configurer le fuseau horaire")
@app_commands.describe(timezone="Fuseau horaire (ex: Europe/Paris)")
async def set_timezone(interaction: discord.Interaction, timezone: str):
    """Commande /set timezone."""
    if not interaction.guild:
        return
    
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(MESSAGES["permission_denied"], ephemeral=True)
        return
    
    # Valider le timezone
    try:
        ZoneInfo(timezone)
    except Exception:
        await interaction.response.send_message(
            f"❌ Fuseau horaire invalide. Exemples: Europe/Paris, America/New_York, UTC",
            ephemeral=True
        )
        return
    
    config = bot.get_guild_config(interaction.guild.id)
    config["timezone"] = timezone
    bot._save_data()
    
    await interaction.response.send_message(
        MESSAGES["set_timezone_success"].format(timezone=timezone)
    )


@set_group.command(name="checkdate", description="Configurer le jour et l'heure de vérification")
@app_commands.describe(
    day="Jour de la semaine (monday, tuesday, wednesday, thursday, friday, saturday, sunday)",
    hour="Heure (0-23)",
    minute="Minute (0-59)"
)
@app_commands.choices(day=[
    app_commands.Choice(name="Lundi", value="monday"),
    app_commands.Choice(name="Mardi", value="tuesday"),
    app_commands.Choice(name="Mercredi", value="wednesday"),
    app_commands.Choice(name="Jeudi", value="thursday"),
    app_commands.Choice(name="Vendredi", value="friday"),
    app_commands.Choice(name="Samedi", value="saturday"),
    app_commands.Choice(name="Dimanche", value="sunday"),
])
async def set_checkdate(interaction: discord.Interaction, day: str, hour: int, minute: int = 0):
    """Commande /set checkdate."""
    if not interaction.guild:
        return
    
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(MESSAGES["permission_denied"], ephemeral=True)
        return
    
    if hour < 0 or hour > 23:
        await interaction.response.send_message("❌ L'heure doit être entre 0 et 23", ephemeral=True)
        return
    
    if minute < 0 or minute > 59:
        await interaction.response.send_message("❌ Les minutes doivent être entre 0 et 59", ephemeral=True)
        return
    
    config = bot.get_guild_config(interaction.guild.id)
    config["check_schedule"] = {
        "day": day,
        "hour": hour,
        "minute": minute
    }
    bot._save_data()
    
    await interaction.response.send_message(
        MESSAGES["set_schedule_success"].format(day=day, hour=hour, minute=minute)
    )


@set_group.command(name="channel", description="Configurer le canal de notifications")
@app_commands.describe(
    notification_type="Type de notification",
    channel="Canal pour les notifications"
)
@app_commands.choices(notification_type=[
    app_commands.Choice(name="Nouveaux produits", value="new_products"),
    app_commands.Choice(name="Produits mis à jour", value="updated_products"),
])
async def set_channel(interaction: discord.Interaction, notification_type: str, channel: discord.TextChannel):
    """Commande /set channel."""
    if not interaction.guild:
        return
    
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(MESSAGES["permission_denied"], ephemeral=True)
        return
    
    config = bot.get_guild_config(interaction.guild.id)
    config["channels"][notification_type] = channel.id
    bot._save_data()
    
    type_label = "nouveaux produits" if notification_type == "new_products" else "produits mis à jour"
    await interaction.response.send_message(
        MESSAGES["set_channel_success"].format(type=type_label, channel=channel.mention)
    )


@app_commands.command(name="check", description="Forcer une vérification immédiate (admin)")
async def check_command(interaction: discord.Interaction):
    """Commande /check pour forcer un check."""
    if not interaction.guild:
        return
    
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(MESSAGES["permission_denied"], ephemeral=True)
        return
    
    config = bot.get_guild_config(interaction.guild.id)
    sellers = config.get("sellers", [])
    
    if not sellers:
        await interaction.response.send_message(MESSAGES["list_empty"])
        return
    
    await interaction.response.send_message(MESSAGES["check_started"])
    
    total_new = 0
    total_updated = 0
    
    for seller_url in sellers:
        try:
            existing_products = bot.products_cache.get(seller_url, {}).get("products", [])
            result = await scrape_seller_with_details(seller_url, existing_products)
            
            if result:
                bot.products_cache[seller_url] = {
                    "last_check": datetime.now().isoformat(),
                    "products": result["products"]
                }
                
                changes = result["changes"]
                total_new += len(changes.get("new", []))
                total_updated += len(changes.get("updated", []))
                
                # Notifier
                if changes["new"] or changes["updated"]:
                    await bot._notify_guilds(seller_url, changes)
                    
        except Exception as e:
            logger.error(f"Erreur check {seller_url}: {e}")
    
    bot._save_data()
    
    if total_new == 0 and total_updated == 0:
        await interaction.followup.send(MESSAGES["check_no_changes"])
    else:
        await interaction.followup.send(
            MESSAGES["check_complete"].format(new=total_new, updated=total_updated)
        )


# ============================================================================
# Point d'entrée
# ============================================================================

if __name__ == '__main__':
    if not TOKEN:
        logger.error("ASSETS_BOT_TOKEN non défini!")
        exit(1)
    
    logger.info("Démarrage du bot Fab Seller Tracker...")
    bot.run(TOKEN)
