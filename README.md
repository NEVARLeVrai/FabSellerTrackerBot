# 🛒 Fab Seller Tracker Bot

Discord Bot to track seller products on [Fab.com](https://fab.com) and receive automatic notifications.

> [!NOTE]
> Currently, this bot is optimized for **Unreal Engine** products. Support for other Fab categories (Unity, Decals, etc.) and features may be expanded in future versions.

## ✨ Features

- 📦 **SQLite Persistence**: Robust and fast data storage (replaces legacy JSON files).
- 🔔 **Smart Notifications**: Tracking for both new products and updates with detailed embeds.
- 📢 **Announcement Publishing**: Auto-publish messages to Discord announcement channels with smart batch system (5 messages/batch, 7 min delay).
- ⏰ **Reactive Scheduler**: Flexible check times (Daily, Weekly, Monthly) that update immediately when changed.
- 🔒 **Synchronization Lock**: Prevents concurrent checks and double notifications (safety first!).
- 🌍 **Global Support**: Multi-server, multi-timezone, and complete multi-language (English/French) - including all logs and system messages.
- 💰 **Accurate Pricing**: Multi-currency support (USD/EUR) with VAT-exclusive extraction and IP-lock bypass.
- 🔗 **Smart Normalization**: Case-insensitive URL standardization to prevent duplicate tracking/notifications.
- 📜 **Changelog & Versions**: Automatic extraction of product logs and supported Unreal Engine versions.
- 🕵️ **Anti-Bot Detection**: Stealth mode integration (Playwright) to ensure reliable scraping.
- 🔔 **Role Mentions**: Advanced mention system (configurable per notification type).
- 📊 **Visual Logging**: Professional boxed headers and progress indicators in the terminal.

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

## 📋 Commands

| Command                                    | Description                                           |
| ------------------------------------------ | ----------------------------------------------------- |
| `/test`                                    | Test bot functionality and send a test message        |
| `/sub <url>`                               | Subscribe to a seller                                 |
| `/unsub <url>`                             | Unsubscribe from a seller                             |
| `/list`                                    | List tracked sellers & check status                   |
| `/set timezone <tz>`                       | Configure timezone (e.g. Europe/Paris)                |
| `/set checkdate <freq> <day> <hour> <min>` | Set schedule (Daily/Weekly/Monthly)                   |
| `/set channel <type> #channel`             | Set channel for New/Updated products                  |
| `/set language <lang>`                     | Set bot language (en or fr)                           |
| `/set currency <curr>`                     | Set global currency (USD, EUR)                        |
| `/set mention <true/false>`                | Enable/disable role mentions                          |
| `/set mention_role <type> <role> <action>` | Add/remove roles to mention                           |
| `/set publish <true/false>`                | Enable/disable auto-publish to announcement followers |
| `/set create_roles`                        | Auto-create default notification roles                |
| `/info`                                    | View bot version and changelog                        |
| `/check now`                               | Force immediate check (protected by sync lock)        |
| `/check config`                            | View server configuration (Admin only)                |

## 📁 Project Structure

```text
├── run.py                 # Core entry point
├── run_bot.bat            # Windows launcher
├── run_bot.sh             # Linux/Mac launcher
├── requirements.txt       # Dependencies
├── LICENSE                # MIT License
├── bot/
    ├── core/              # Main logic, config, database & language managers
    ├── models/            # Data models (Product, GuildConfig)
    ├── services/          # Scraper & external services (scraper.py)
    ├── resources/         # Static resources and persistent data
        ├── database/      # tracker.db (SQLite)
        ├── json/          # version.json
        ├── lang/          # Translation files (en.json, fr.json)
        └── logs/          # bot.log
    └── tools/             # verify_structure.py, reset_bot.py, export_to_json.py
```

### ⚡ Quick Start

1. **Subscribe** to a seller: `/sub https://fab.com/sellers/gameassetfactory`
2. **Set Channels** (Mandatory):
   - `/set channel type:New #news`
   - `/set channel type:Updated #alerts`
3. **Configure Schedule**: `/set checkdate frequency:Daily hour:10 minute:0`
4. **Set Currency**: `/set currency USD`
5. **Set Language**: `/set language en`
6. **Enable Publishing** (Optional - for announcement channels): `/set publish true`
7. **Test & Verify**: `/test` or `/check now`

> [!TIP]
> To use the auto-publish feature, your notification channels must be **Announcement Channels** (News type). Discord limits publishing to 10 messages per hour.

The bot detects product updates based on 4 criteria (in order of priority):
1. **Last Update Date** — When the product's update date changes
2. **Changelog** — When new changelog entries are added
3. **UE Versions** — When supported Unreal Engine versions change
4. **Price** — When the product price changes

## 📜 License

[MIT License](https://github.com/NEVARLeVrai/FabSellerTrackerBot?tab=License-1-ov-file)

**Developed with ❤️ in Python by [NEVAR](https://github.com/NEVARLeVrai)**