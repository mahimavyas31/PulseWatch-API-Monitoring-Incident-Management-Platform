from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./pulsewatch.db"
    secret_key: str = "dev-secret-change-me"
    token_expire_minutes: int = 60 * 24
    cookie_secure: bool = False  # set true when serving over HTTPS

    # Monitoring behaviour
    allow_private_targets: bool = False  # SSRF protection ON by default
    failure_threshold: int = 3  # consecutive failures before an incident opens
    degraded_ms: int = 1500  # slower than this => "degraded"
    scheduler_tick_seconds: int = 10
    max_workers: int = 10
    retention_days: int = 30
    embedded_scheduler: bool = False
    auto_create_tables: bool = False  # dev shortcut; production uses `alembic upgrade head`

    # Anomaly detection (rolling mean / standard deviation on response time)
    anomaly_window: int = 30  # how many recent successful checks form the baseline
    anomaly_min_samples: int = 10  # need at least this much history
    anomaly_z_threshold: float = 3.0
    anomaly_min_delta_ms: int = 200  # ignore tiny absolute changes even if z is high

    # Optional SMTP for alerts
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "pulsewatch@example.com"
    smtp_use_tls: bool = True

    log_level: str = "INFO"

    @field_validator("database_url")
    @classmethod
    def normalise_db_url(cls, v: str) -> str:
        # Hosts like Render hand out postgres:// or postgresql:// URLs.
        if v.startswith("postgres://"):
            v = "postgresql://" + v[len("postgres://"):]
        if v.startswith("postgresql://"):
            v = "postgresql+psycopg://" + v[len("postgresql://"):]
        return v


settings = Settings()
