# 🛒 Fab Seller Tracker Bot

Discord Bot to track seller products on [Fab.com](https://fab.com) and receive automatic notifications.

## ✨ Features

- 📦 Track multiple Fab.com sellers
- 🔔 Notifications for new products and updates
- ⏰ Scheduled checks (configurable)
- 🌍 Multi-server and multi-timezone support
- Multi-language support (English/French)
- 💰 Multi-currency support (USD/EUR)
- 📝 Multi-license price display

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
Update the path in `token_file` within `bot/config.py`.

### 3. Run the bot

The bot will automatically check and install missing dependencies on the first run.

**Windows:**
Double-click on `run_bot.bat`

**Linux / Mac:**

```bash
bash run_bot.sh
```

_(Or manually: `python run.py`)_

## 📋 Discord Commands

| Command                        | Description                            |
| ------------------------------ | -------------------------------------- |
| `/sub <url>`                   | Subscribe to a seller                  |
| `/unsub <url>`                 | Unsubscribe from a seller              |
| `/list`                        | List tracked sellers                   |
| `/set timezone <tz>`           | Configure timezone (e.g. Europe/Paris) |
| `/set checkdate <day> <hour>`  | Configure check schedule               |
| `/set channel <type> #channel` | Set channel for New/Updated products   |
| `/set language <lang>`         | Set bot language (en or fr)            |
| `/set currency <curr>`         | Set global currency (USD, EUR)         |
| `/check`                       | Force immediate check (Admin only)     |

## 📁 Project Structure

```
├── run.py            # Entry point
├── bot/              # Source code
│   ├── config.py     # Configuration
│   ├── scraper.py    # Fab.com scraper
│   ├── lang.py       # Language manager
│   └── main.py       # Main Discord Bot
├── data/             # Saved data
│   ├── sellers_subscriptions.json
│   ├── products_cache.json
│   └── lang/         # Language files
└── requirements.txt  # Python dependencies
```

## 📝 Usage Example

```
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
