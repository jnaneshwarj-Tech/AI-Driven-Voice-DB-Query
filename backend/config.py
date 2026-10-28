import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    MYSQL_HOST: str = "localhost"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "root"
    MYSQL_PASSWORD: str = ""
    MYSQL_DB: str = "student_db"

    SECRET_KEY: str = ""
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.6-flash"
    GEMINI_FALLBACK_MODEL: str = "gemini-3.1-flash-lite"

    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 1000

    # ── Application identity ──────────────────────────────────────────────────
    APP_NAME: str = "AI Database Automator"

    # ── Email / SMTP Settings ─────────────────────────────────────────────────
    MAIL_SERVER: str = "smtp.gmail.com"
    MAIL_PORT: int = 587
    MAIL_USERNAME: str = ""
    MAIL_PASSWORD: str = ""
    MAIL_USE_TLS: bool = True
    MAIL_FROM: str = ""
    MAIL_FROM_NAME: str = "AI Database Automator"
    FRONTEND_URL: str = "http://localhost:5173"
    ALLOWED_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000"

    # ── OTP / Password Reset Settings ─────────────────────────────────────────
    OTP_EXPIRY_SECONDS: int = 120          # 2 minutes
    OTP_RESEND_COOLDOWN_SECONDS: int = 30  # 30-second cooldown between resends
    OTP_MAX_ATTEMPTS: int = 5              # max wrong OTP attempts before lock
    RESET_TOKEN_EXPIRY_MINUTES: int = 10   # reset_token validity after OTP verified
    OTP_MAX_REQUESTS_PER_HOUR: int = 5     # rate-limit: max OTP requests per email/hour

    # ── Sprint 1 — Backup / Recovery settings ─────────────────────────────────
    BACKUP_DIR: str = "backups"
    BACKUP_RETENTION_DAILY: int = 7
    BACKUP_RETENTION_WEEKLY: int = 4
    BACKUP_AUTO_ENABLED: bool = True
    UPLOAD_DIR: str = "uploads"
    MAX_UPLOAD_ROWS_PER_CHUNK: int = 500
    UNDO_WINDOW_MINUTES_SINGLE: int = 5
    UNDO_WINDOW_MINUTES_BULK: int = 30
    UNDO_RETENTION_DAYS: int = 30

    model_config = SettingsConfigDict(
        env_file=[os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"), ".env"],
        env_file_encoding="utf-8",
        extra="ignore"
    )

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

    def validate_startup(self):
        """
        Validates required configuration variables safely at startup.
        Never displays secret values in error messages.
        """
        missing = []
        if not (self.SECRET_KEY and self.SECRET_KEY.strip()):
            missing.append("SECRET_KEY")
        if not (self.MYSQL_DB and self.MYSQL_DB.strip()):
            missing.append("MYSQL_DB")
        if not (self.MYSQL_USER and self.MYSQL_USER.strip()):
            missing.append("MYSQL_USER")

        if missing:
            raise RuntimeError(
                f"[CONFIG ERROR] Startup failed due to missing required variable(s): {', '.join(missing)}. "
                f"Please configure them in your backend/.env file (see backend/.env.example)."
            )

settings = Settings()
