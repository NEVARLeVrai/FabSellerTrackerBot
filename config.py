# -*- coding: utf-8 -*-
"""
Configuration pour Fab Seller Tracker Bot
"""
import os

# Chemins
PATHS = {
    'token_file': "C:/Users/Danie/Mon Drive/Autres/Bot Python Discord/token_fab.txt",
    'data_folder': "./data/",
    'log_file': "./data/logs/bot.log",
    'sellers_file': "sellers_subscriptions.json",
    'products_cache_file': "products_cache.json",
}

# Lire le token depuis le fichier
def get_token() -> str:
    """Lit le token Discord depuis le fichier."""
    token_path = PATHS['token_file']
    if os.path.exists(token_path):
        with open(token_path, 'r', encoding='utf-8') as f:
            return f.read().strip()
    return os.environ.get("ASSETS_BOT_TOKEN", "")

TOKEN = get_token()

# Chemins des données (pour compatibilité)
DATA_FOLDER = PATHS['data_folder']
SELLERS_FILE = PATHS['sellers_file']
PRODUCTS_CACHE_FILE = PATHS['products_cache_file']
LOG_FILE = PATHS['log_file']

# Schedule par défaut
DEFAULT_CHECK_SCHEDULE = {
    "day": "sunday",
    "hour": 0,
    "minute": 0
}

# Timezone par défaut
DEFAULT_TIMEZONE = "Europe/Paris"

# Jours de la semaine (pour le scheduler)
WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6
}

# URLs Fab.com
FAB_BASE_URL = "https://www.fab.com"
FAB_SELLERS_URL = f"{FAB_BASE_URL}/sellers/"
FAB_LISTINGS_URL = f"{FAB_BASE_URL}/listings/"

# Délais et limites
SCRAPE_RETRY_COUNT = 3
SCRAPE_DELAY_MIN = 2.0  # secondes entre requêtes
SCRAPE_DELAY_MAX = 5.0
PAGE_LOAD_TIMEOUT = 60000  # ms
SCROLL_DELAY = 1.0  # secondes

# Couleurs Discord (embeds)
COLOR_NEW_PRODUCT = 0x00FF00  # Vert
COLOR_UPDATED_PRODUCT = 0x3498DB  # Bleu
COLOR_ERROR = 0xFF0000  # Rouge
COLOR_INFO = 0x9B59B6  # Violet

# Messages en français
MESSAGES = {
    "sub_success": "✅ Abonnement ajouté pour le seller : **{seller}**",
    "sub_already": "ℹ️ Vous êtes déjà abonné à ce seller.",
    "sub_invalid_url": "❌ URL invalide. Utilisez le format : `https://fab.com/sellers/NomDuSeller`",
    "unsub_success": "✅ Désabonnement effectué pour : **{seller}**",
    "unsub_not_found": "ℹ️ Vous n'êtes pas abonné à ce seller.",
    "list_empty": "📭 Aucun seller suivi pour le moment.",
    "list_header": "📋 **Sellers suivis :**",
    "set_timezone_success": "✅ Fuseau horaire configuré : **{timezone}**",
    "set_schedule_success": "✅ Vérification planifiée : **{day}** à **{hour}:{minute}**",
    "set_channel_success": "✅ Canal configuré pour **{type}** : {channel}",
    "check_started": "🔄 Vérification en cours...",
    "check_complete": "✅ Vérification terminée. {new} nouveau(x), {updated} mis à jour.",
    "check_no_changes": "✅ Aucun changement détecté.",
    "new_product": "🆕 Nouveau produit",
    "updated_product": "🔄 Produit mis à jour",
    "error_generic": "❌ Une erreur s'est produite. Réessayez plus tard.",
    "error_scraping": "❌ Impossible de récupérer les données du seller.",
    "permission_denied": "❌ Vous n'avez pas la permission d'utiliser cette commande.",
}
