from __future__ import annotations

from dataclasses import dataclass
import os
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv()


def _csv(name: str, default: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in os.getenv(name, default).split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    app_name: str = "atm-cash-intelligence"
    environment: str = os.getenv("ENVIRONMENT", "development")
    database_url: str = os.getenv(
        "DATABASE_URL",
        "sqlite:///./atm_cash.db",
    )
    secret_key: str = os.getenv("SECRET_KEY", "dev-secret-key")
    jwt_secret_key: str = os.getenv("JWT_SECRET_KEY", "")
    jwt_expiration_minutes: int = int(os.getenv("JWT_EXPIRATION_MINUTES", "30"))
    bootstrap_admin_username: str | None = os.getenv("BOOTSTRAP_ADMIN_USERNAME")
    bootstrap_admin_password: str | None = os.getenv("BOOTSTRAP_ADMIN_PASSWORD")
    telegram_token: str | None = os.getenv("TELEGRAM_BOT_TOKEN")
    telegram_bot_username: str | None = os.getenv("TELEGRAM_BOT_USERNAME")
    telegram_webhook_secret: str | None = os.getenv("TELEGRAM_WEBHOOK_SECRET")
    telegram_webhook_url: str | None = os.getenv("TELEGRAM_WEBHOOK_URL")
    smtp_host: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    smtp_username: str | None = os.getenv("SMTP_USERNAME")
    smtp_password: str | None = os.getenv("SMTP_PASSWORD")
    smtp_from_email: str | None = os.getenv("SMTP_FROM_EMAIL")
    notification_email_provider: str = os.getenv("NOTIFICATION_EMAIL_PROVIDER", "smtp").lower()
    gmail_api_client_id: str | None = os.getenv("GMAIL_API_CLIENT_ID")
    gmail_api_client_secret: str | None = os.getenv("GMAIL_API_CLIENT_SECRET")
    gmail_api_refresh_token: str | None = os.getenv("GMAIL_API_REFRESH_TOKEN")
    gmail_api_sender_email: str | None = os.getenv("GMAIL_API_SENDER_EMAIL")
    notification_email_recipients: tuple[str, ...] = tuple(
        address.strip()
        for address in os.getenv("NOTIFICATION_EMAIL_RECIPIENTS", "").split(",")
        if address.strip()
    )
    risk_warning_threshold: float = float(os.getenv("RISK_WARNING_THRESHOLD", "1.0"))
    risk_high_threshold: float = float(os.getenv("RISK_HIGH_THRESHOLD", "0.5"))
    risk_critical_threshold: float = float(os.getenv("RISK_CRITICAL_THRESHOLD", "0.25"))
    risk_safety_buffer: float = float(os.getenv("RISK_SAFETY_BUFFER", "0.25"))
    cors_origins: tuple[str, ...] = _csv("CORS_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173")
    login_rate_limit_attempts: int = int(os.getenv("LOGIN_RATE_LIMIT_ATTEMPTS", "5"))
    login_rate_limit_window_seconds: int = int(os.getenv("LOGIN_RATE_LIMIT_WINDOW_SECONDS", "60"))
    login_rate_limit_block_seconds: int = int(os.getenv("LOGIN_RATE_LIMIT_BLOCK_SECONDS", "300"))
    db_pool_size: int = int(os.getenv("DB_POOL_SIZE", "5"))
    db_max_overflow: int = int(os.getenv("DB_MAX_OVERFLOW", "10"))
    db_pool_timeout_seconds: int = int(os.getenv("DB_POOL_TIMEOUT_SECONDS", "30"))
    request_body_limit_bytes: int = int(os.getenv("REQUEST_BODY_LIMIT_BYTES", "1048576"))
    async_notifications: bool = os.getenv("ASYNC_NOTIFICATIONS", "false").lower() == "true"

    def validate(self) -> None:
        if self.environment not in {"development", "test", "production"}:
            raise RuntimeError("ENVIRONMENT must be development, test, or production")
        if self.jwt_expiration_minutes < 1:
            raise RuntimeError("JWT_EXPIRATION_MINUTES must be at least 1")
        if self.login_rate_limit_attempts < 1 or self.login_rate_limit_window_seconds < 1:
            raise RuntimeError("Login rate-limit settings must be positive")
        if self.notification_email_provider not in {"smtp", "gmail_api"}:
            raise RuntimeError("NOTIFICATION_EMAIL_PROVIDER must be smtp or gmail_api")
        if self.environment == "production":
            if len(self.jwt_secret_key) < 32:
                raise RuntimeError("JWT_SECRET_KEY must be configured with at least 32 characters")
            if self.database_url.startswith("sqlite"):
                raise RuntimeError("Production requires PostgreSQL via DATABASE_URL")
            if not self.cors_origins:
                raise RuntimeError("CORS_ORIGINS must contain at least one trusted origin")
            if any(origin == "*" for origin in self.cors_origins):
                raise RuntimeError("Wildcard CORS origins are not allowed in production")
            parsed = urlparse(self.database_url)
            if parsed.scheme not in {"postgresql", "postgres", "postgresql+psycopg", "postgresql+psycopg2"}:
                raise RuntimeError("Production DATABASE_URL must use PostgreSQL")


settings = Settings()
