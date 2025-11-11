# Easystaff Helper

A Telegram bot that converts rubles to euros.
You enter an amount, and the bot converts it to euros using rates from xe.com and invoice.easystaff.io. The bot selects the most favorable amount if the difference between the amounts does not exceed 10% and displays it to the user.

![Easystaff Helper logo](logo.png)


## Architecture

    Bot: aiogram Dispatcher + command and message handlers.

    Services:
        XeConverterService (aiohttp + BeautifulSoup) returns EUR amount.
        EasystaffService (Playwright) returns RUB/EUR rate.
        NotificationService (admin broadcasts).
        Scheduler (aiocron, TZ-aware) check the rate 3 times a day and save it to the cache.

    Database (optional):
        AsyncDatabaseConnection (asyncmy, ping + auto-reconnect).
        StatsRepository (users + usage stats).

    Cache: CacheRepository (JSON with rate + updated_at ISO timestamp).

    Utils: format_datetime (TZ-aware), trunc2 (truncate to 2 decimals).

    Commands:
        /start - greet.
        /stats - totals + top users (if DB enabled), for admin.


## Quick Start (Docker Compose)
### ENV
Rename  ```.env.example``` to ```.env```

Fill vars:
```
TELEGRAM_BOT_TOKEN=
ADMIN_IDS=
EASYSTAFF_EMAIL=
EASYSTAFF_PASSWORD=
TRACING_ENABLED=false # True if you want to trace Playwright
```

### Unix, automatic installation.
The entire installation is automated (Ubuntu tested); during the installation process, you can enable the use of a database for collecting statistics.

```bash
bash <(curl -Ls https://raw.githubusercontent.com/accountuse/easystaff-helper-bot/master/install.sh)
```

or
```
git clone https://github.com/accountuse/easystaff-helper-bot.git
cd easystaff-helper-bot
chmod +x install.sh
sudo ./install.sh
```


### Unix, manual installation
```
sudo apt update
sudo apt install -y apt-transport-https ca-certificates curl gnupg lsb-release
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo usermod -aG docker $USER
docker compose up -d

# Automatic startup Docker service ON/OFF
sudo systemctl status docker
sudo systemctl enable docker
sudo systemctl disable docker
```
to use the database (optional):

.env
```
USE_DB=true
```
```
cd easystaff-helper-bot
docker cp easystaff-helper.sql easystaff-helper-db:/tmp/easystaff-helper.sql
docker exec -it easystaff-helper-db bash
mariadb -uroot -p1234 < /tmp/easystaff-helper.sql
docker compose down
docker compose up -d
```

delete external root from DB (optional)
```
SELECT user,host FROM mysql.user WHERE user='root';
DROP USER 'root'@'%';
DROP USER 'root'@'0.0.0.0';
FLUSH PRIVILEGES;
```

The project code was created in Perplexity AI.
