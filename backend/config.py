import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    MYSQL_HOST: str = "localhost"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "root"
    MYSQL_PASSWORD: str = "Manoj@123"
    MYSQL_DB: str = "student_db"

    SECRET_KEY: str = "supersecretkey_change_in_prod"
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.6-flash"
    GEMINI_FALLBACK_MODEL: str = "gemini-3.5-flash"

    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 1000

    # Sprint 1 — Backup / Recovery settings
    BACKUP_DIR: str = "backups"
    BACKUP_RETENTION_DAILY: int = 7        # keep last N daily backups
    BACKUP_RETENTION_WEEKLY: int = 4       # keep last N weekly backups
    BACKUP_AUTO_ENABLED: bool = True       # auto-backup on schedule
    UPLOAD_DIR: str = "uploads"            # persistent upload cache
    MAX_UPLOAD_ROWS_PER_CHUNK: int = 500   # batch size for large uploads
    UNDO_WINDOW_MINUTES_SINGLE: int = 5    # undo window for single ops
    UNDO_WINDOW_MINUTES_BULK: int = 30     # undo window for bulk/upload ops
    UNDO_RETENTION_DAYS: int = 30          # retain committed rollback snapshots

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def JWT_SECRET_KEY(self) -> str:
        return self.SECRET_KEY

    @property
    def backup_dir_abs(self) -> str:
        """Absolute path to the backup directory."""
        base = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(base, self.BACKUP_DIR)
        os.makedirs(path, exist_ok=True)
        return path

    @property
    def upload_dir_abs(self) -> str:
        """Absolute path to the persistent upload cache directory."""
        base = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(base, self.UPLOAD_DIR)
        os.makedirs(path, exist_ok=True)
        return path

settings = Settings()
# Force reload
