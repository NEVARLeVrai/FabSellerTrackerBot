# 🛒 Fab Seller Tracker Bot

Discord Bot to track seller products on [Fab.com](https://fab.com) and receive automatic notifications.

## ✨ Features

- 📦 Track multiple Fab.com sellers
- 🔔 Notifications for new products and updates
- ⏰ Scheduled checks (configurable)
- 🌍 Multi-server and multi-timezone support
- 🌍 Multi-server and multi-timezone support
- 🌐 Multi-language support (English/French)
- 💰 Multi-currency support (USD/EUR/GBP)
- 📝 Multi-license price display

## 🚀 Installation

### 1. Clone the repo

```bash
git clone https://github.com/NEVARLeVrai/FabSellerTrackerBot.git
cd FabSellerTrackerBot
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Install Playwright (browser)

```bash
python -m playwright install firefox
```

### 4. Configure Discord Token

**Windows:**

```cmd
in the config.py file
```

### 5. Run the bot

```bash
python run.py
```

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
| `/set currency <curr>`         | Set global currency (USD, EUR, GBP)    |
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
