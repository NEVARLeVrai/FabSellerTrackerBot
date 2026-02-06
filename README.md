# 🛒 Fab Seller Tracker Bot

Discord Bot to track seller products on [Fab.com](https://fab.com) and receive automatic notifications.

> [!NOTE]
> Currently, this bot is optimized for **Unreal Engine** products. Support for other Fab categories (Unity, Decals, etc.) and features may be expanded in future versions.

## ✨ Features

- 📦 **SQLite Persistence**: Robust and fast data storage (replaces legacy JSON files).
- 🔔 **Smart Notifications**: Tracking for both new products and updates with detailed embeds.
- ⏰ **Scheduled Checks**: Fully configurable check times per guild.
- 🌍 **Global Support**: Multi-server, multi-timezone, and multi-language (English/French).
- 💰 **Accurate Pricing**: Multi-currency support (USD/EUR) with VAT-exclusive extraction and IP-lock bypass.
- 📜 **Changelog & Versions**: Automatic extraction of product logs and supported Unreal Engine versions.
- �️ **Anti-Bot Detection**: Stealth mode integration (Playwright) to ensure reliable scraping.
- 🔔 **Role Mentions**: Advanced mention system (configurable per notification type).
- 🛠️ **Maintenance Suite**: Built-in tools for structure verification and complete data reset.

## 🚀 Installation

### 📋 Prerequisites

- **Python 3.9** or higher ([Download here](https://www.python.org/downloads/))

### 1. Clone & Setup

```bash
git clone https://github.com/NEVARLeVrai/FabSellerTrackerBot.git
cd FabSellerTrackerBot
```

### 2. Configure Token (3 Options)

You can choose one of the following methods:

**Option 1: Local File (Recommended)**
Create a file named `token.txt` in the root folder and paste your Discord Bot Token inside.

**Option 2: Environment Variable**
Set the `ASSETS_BOT_TOKEN` environment variable.

**Option 3: Legacy File**
Update the path in `PATHS['token_file']` within `bot/core/config.py`.

### 3. Run the bot

The bot will automatically check and install missing dependencies on the first run, including Playwright browsers and the Stealth plugin.

**Windows:**
Double-click on `run_bot.bat`

**Linux / Mac:**

```bash
bash run_bot.sh
```

_(Or manually: `python run.py`)_

## 📋 Discord Commands

| Command                                    | Description                            |
| ------------------------------------------ | -------------------------------------- |
| `/sub <url>`                               | Subscribe to a seller                  |
| `/unsub <url>`                             | Unsubscribe from a seller              |
| `/list`                                    | List tracked sellers & check status    |
| `/set timezone <tz>`                       | Configure timezone (e.g. Europe/Paris) |
| `/set checkdate <day> <hour>`              | Configure check schedule               |
| `/set channel <type> #channel`             | Set channel for New/Updated products   |
| `/set language <lang>`                     | Set bot language (en or fr)            |
| `/set currency <curr>`                     | Set global currency (USD, EUR)         |
| `/set mention <true/false>`                | Enable/disable role mentions           |
| `/set mention_role <type> <role> <action>` | Add/remove roles to mention            |
| `/set create_roles`                        | Auto-create default notification roles |
| `/info`                                    | View bot version and changelog         |
| `/check`                                   | Force immediate check (Admin only)     |

## 📁 Project Structure

```text
├── run.py                 # Core entry point
├── run_bot.bat            # Windows launcher
├── run_bot.sh             # Linux/Mac launcher
├── requirements.txt       # Dependencies
├── LICENSE                # MIT License
├── bot/
│   ├── core/              # Main logic, config, database & language managers
│   ├── models/            # Data models (Product, GuildConfig)
│   ├── services/          # Scraper & external services (scraper.py)
│   ├── resources/         # Static resources and persistent data
│   │   ├── database/      # tracker.db (SQLite)
│   │   ├── json/          # version.json, legacy JSON files
│   │   ├── lang/          # Translation files (en.json, fr.json)
│   │   └── logs/          # bot.log
│   └── tools/             # verify_structure.py, reset_bot.py
```

## 📝 Usage Example

```text
/sub https://fab.com/sellers/GameAssetFactory
/set timezone Europe/Paris
/set checkdate sunday 0 0
/set channel new_products #news
/set language fr
/set currency EUR
```

## 📜 License

[MIT License](https://github.com/NEVARLeVrai/FabSellerTrackerBot?tab=License-1-ov-file)

**Developed with ❤️ in Python by [NEVAR](https://github.com/NEVARLeVrai)**
