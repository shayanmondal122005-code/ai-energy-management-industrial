from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    app_name: str = "MicroGrid AI"
    app_version: str = "2.0.0"
    debug: bool = False
    environment: str = "production"  # development | staging | production

    # Database (Supabase PostgreSQL)
    database_url: str = ""
    db_pool_size: int = 10
    db_max_overflow: int = 20

    # Supabase
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""  # backend only — never expose to frontend

    # Redis (Upstash)
    redis_url: str = ""

    # JWT
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60
    jwt_refresh_token_expire_days: int = 30

    # Twilio WhatsApp
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_whatsapp_from: str = "whatsapp:+14155238886"  # Twilio sandbox default

    # Sentry
    sentry_dsn: str = ""

    # Open-Meteo (no key needed — free)
    open_meteo_base_url: str = "https://api.open-meteo.com/v1"

    # Supabase Storage (PDF reports)
    storage_bucket_reports: str = "reports"

    # Facility defaults (Kolkata)
    default_lat: float = 22.57
    default_lon: float = 88.36
    default_timezone: str = "Asia/Kolkata"

    # Rate limiting
    rate_limit_public: str = "10/minute"
    rate_limit_authenticated: str = "100/minute"
    rate_limit_iot_ingest: str = "10/minute"
    rate_limit_control: str = "5/minute"
    rate_limit_login: str = "5/minute"

    # Background jobs
    decision_cycle_interval_minutes: int = 15
    alert_check_interval_minutes: int = 5
    model_retrain_interval_hours: int = 1
    weekly_report_day: str = "monday"
    weekly_report_hour_ist: int = 8

    # Model quality gate
    max_acceptable_mape: float = 15.0

    # Control command safety
    command_confirmation_timeout_seconds: int = 60


@lru_cache
def get_settings() -> Settings:
    return Settings()
