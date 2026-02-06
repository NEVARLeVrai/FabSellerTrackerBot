# 🛒 Fab Seller Tracker Bot

Bot Discord pour suivre les produits de sellers sur [Fab.com](https://fab.com) et recevoir des notifications automatiques.

## ✨ Fonctionnalités

- 📦 Suivi de multiples sellers Fab.com
- 🔔 Notifications pour nouveaux produits et mises à jour
- ⏰ Vérifications planifiées (configurable)
- 🌍 Support multi-serveurs et multi-fuseaux horaires
- 🇫🇷 Messages en français

## 🚀 Installation

### 1. Cloner le repo

```bash
git clone https://github.com/votre-repo/FabSellerTrackerBot.git
cd FabSellerTrackerBot
```

### 2. Installer les dépendances

```bash
pip install -r requirements.txt
```

### 3. Installer Playwright (navigateur)

```bash
python -m playwright install firefox
```

### 4. Configurer le token Discord

**Windows:**

```cmd
set ASSETS_BOT_TOKEN=votre_token_discord
```

**Linux/Mac:**

```bash
export ASSETS_BOT_TOKEN=votre_token_discord
```

### 5. Lancer le bot

```bash
python main.py
```

## 📋 Commandes Discord

| Commande                                | Description                              |
| --------------------------------------- | ---------------------------------------- |
| `/sub <url>`                            | S'abonner à un seller                    |
| `/unsub <url>`                          | Se désabonner d'un seller                |
| `/list`                                 | Voir les sellers suivis                  |
| `/set timezone <tz>`                    | Configurer le fuseau horaire             |
| `/set checkdate <jour> <heure>`         | Configurer le jour/heure de vérification |
| `/set channel newproducts #channel`     | Canal pour nouveaux produits             |
| `/set channel updatedproducts #channel` | Canal pour mises à jour                  |
| `/check`                                | Forcer une vérification immédiate        |

## 📁 Structure du projet

```
├── config.py         # Configuration et messages
├── scraper.py        # Scraping Fab.com
├── main.py           # Bot Discord principal
├── requirements.txt  # Dépendances Python
└── data/             # Données sauvegardées (créé automatiquement)
    ├── sellers_subscriptions.json
    └── products_cache.json
```

## 📝 Exemple d'utilisation

```
/sub https://fab.com/sellers/GameAssetFactory
/set timezone Europe/Paris
/set checkdate sunday 0 0
/set channel newproducts #nouveautes
```

## 📜 License

MIT License
