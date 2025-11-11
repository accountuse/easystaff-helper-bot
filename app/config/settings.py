from pathlib import Path
from dotenv import load_dotenv
import os
import pytz

load_dotenv(Path(__file__).parent.parent / '.env', override=True)

def env_bool(name: str, default: bool = False) -> bool:
    return str(os.getenv(name, str(default))).strip().lower() in {"1", "true", "yes", "on", "y", "t"}

class Settings:
    # For debugging Easystaff
    TRACING_ENABLED = env_bool("TRACING_ENABLED", False)

    # Telegram
    API_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()]

    # Easystaff
    EASYSTAFF_EMAIL = os.getenv('EASYSTAFF_EMAIL')
    EASYSTAFF_PASSWORD = os.getenv('EASYSTAFF_PASSWORD')
    EASYSTAFF_URL = os.getenv('EASYSTAFF_URL')

    # XE
    XE_URL = os.getenv('XE_URL')

    # Directories
    BASE_DIR = Path("/app")
    STORAGE_DIR = BASE_DIR / "storage"

    # Artifacts
    ARTIFACTS_DIR = STORAGE_DIR / "artifacts"
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    # Cache
    CACHE_DIR = STORAGE_DIR / "cache"
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_FILE = CACHE_DIR / "easystaff_rate.json"

    # Logs
    LOGS_DIR = STORAGE_DIR / "logs"
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    LOG_FILE = LOGS_DIR / "errors.log"

    # Timezone
    SERVER_TZ = pytz.timezone(os.getenv('SERVER_TZ')) if os.getenv('SERVER_TZ') else pytz.UTC

    # Cron
    MORNING_CRON = os.getenv('MORNING_CRON')
    DAILY_CRON = os.getenv('DAILY_CRON')
    AFTERNOON_CRON = os.getenv('AFTERNOON_CRON')

    # Database
    USE_DB = env_bool("USE_DB", False)
    DB_USER = os.getenv('DB_USER')
    DB_PASSWORD = os.getenv('DB_PASSWORD')
    DB_HOST = os.getenv('DB_HOST')
    DB_PORT = int(os.getenv('DB_PORT', 3306))
    DB_NAME = os.getenv('DB_NAME')
