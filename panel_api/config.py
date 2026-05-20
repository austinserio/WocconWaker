"""Panel configuration from environment."""
import os
from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class PanelSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite:///./data/woccon.db"
    jwt_secret: str = "change-me-in-production"
    jwt_expire_minutes: int = 1440
    jwt_algorithm: str = "HS256"
    panel_admin_email: str = "admin@woccon.local"
    panel_admin_password: str = "changeme"
    panel_cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    woccon_upload_dir: str = "data/uploads"
    duplicate_threshold: float = 0.85
    dictionary_unified_path: str = "woccon_language/dictionary_unified.json"
    rules_unified_path: str = "woccon_language/rules_unified.json"
    dictionary_legacy_path: str = "woccon_language/dictionary.json"
    rules_legacy_path: str = "woccon_language/rules.json"
    pending_duplicate_days: int = 30

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.panel_cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> PanelSettings:
    return PanelSettings(
        database_url=os.environ.get("DATABASE_URL", "sqlite:///./data/woccon.db"),
        jwt_secret=os.environ.get("JWT_SECRET", "change-me-in-production"),
        jwt_expire_minutes=int(os.environ.get("JWT_EXPIRE_MINUTES", "1440")),
        panel_admin_email=os.environ.get("PANEL_ADMIN_EMAIL", "admin@woccon.local"),
        panel_admin_password=os.environ.get("PANEL_ADMIN_PASSWORD", "changeme"),
        panel_cors_origins=os.environ.get(
            "PANEL_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
        ),
        woccon_upload_dir=os.environ.get("WOCCON_UPLOAD_DIR", "data/uploads"),
        duplicate_threshold=float(os.environ.get("DUPLICATE_THRESHOLD", "0.85")),
        dictionary_unified_path=os.environ.get(
            "WOCCON_DICTIONARY_PATH", "woccon_language/dictionary_unified.json"
        ),
        rules_unified_path=os.environ.get("WOCCON_RULES_PATH", "woccon_language/rules_unified.json"),
        dictionary_legacy_path=os.environ.get(
            "WOCCON_DICTIONARY_LEGACY_PATH", "woccon_language/dictionary.json"
        ),
        rules_legacy_path=os.environ.get("WOCCON_RULES_LEGACY_PATH", "woccon_language/rules.json"),
    )
