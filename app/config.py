"""
Configuration centrale de l'application.
Toutes les valeurs sensibles viennent du fichier .env (jamais committe, jamais transmis
a un tiers autre que OANDA / FRED directement depuis votre machine).
"""
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _get_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


class Settings:
    APP_MODE: str = os.getenv("APP_MODE", "demo").strip().lower()  # "demo" | "live"

    OANDA_API_KEY: str = os.getenv("OANDA_API_KEY", "")
    OANDA_ACCOUNT_ID: str = os.getenv("OANDA_ACCOUNT_ID", "")
    OANDA_ENV: str = os.getenv("OANDA_ENV", "practice").strip().lower()  # "practice" | "live"

    FRED_API_KEY: str = os.getenv("FRED_API_KEY", "")

    GOLD_INSTRUMENT: str = os.getenv("GOLD_INSTRUMENT", "XAU_USD")
    DISPLAY_TZ: str = os.getenv("DISPLAY_TZ", "Asia/Dubai")

    # Protection par mot de passe du dashboard (HTTP Basic Auth). Vide = pas de
    # protection (usage local). Toujours defini en production sur Vercel.
    DASHBOARD_PASSWORD: str = os.getenv("DASHBOARD_PASSWORD", "")

    DB_PATH: Path = BASE_DIR / "journal.db"
    CALENDAR_PATH: Path = BASE_DIR / "data" / "risk_calendar.json"

    @property
    def database_url(self) -> str:
        """URL Postgres, injectee automatiquement par Vercel Postgres (POSTGRES_URL)
        ou definie manuellement (DATABASE_URL). Vide = on reste sur SQLite local."""
        return os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL") or ""

    @property
    def oanda_base_url(self) -> str:
        if self.OANDA_ENV == "live":
            return "https://api-fxtrade.oanda.com"
        return "https://api-fxpractice.oanda.com"

    @property
    def is_demo(self) -> bool:
        return self.APP_MODE != "live"

    @property
    def oanda_configured(self) -> bool:
        return bool(self.OANDA_API_KEY and self.OANDA_ACCOUNT_ID)


settings = Settings()
