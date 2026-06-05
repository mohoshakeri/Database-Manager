from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_LOGO_URL = "/static/img/logo.png"
DEFAULT_FAVICON_URL = "/static/img/favicon.ico"


def _bool_from_env(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    debug: bool = Field(default=False, validation_alias="DEBUG")
    port: int = Field(default=80, validation_alias="PORT")
    base_url: str = Field(default="http://localhost", validation_alias="BASE_URL")
    cors_alloweds: str = Field(default="", validation_alias="CORS_ALLOWEDS")

    app_username: str = Field(default="admin", validation_alias="BACKUP_HUB_USERNAME")
    app_password: str = Field(default="", validation_alias="BACKUP_HUB_PASSWORD")
    app_password_hash: str = Field(default="", validation_alias="BACKUP_HUB_PASSWORD_HASH")
    totp_secret: str = Field(default="", validation_alias="BACKUP_HUB_TOTP_SECRET")
    session_secret: str = Field(default="", validation_alias="BACKUP_HUB_SESSION_SECRET")
    session_cookie: str = Field(default="dbm_session", validation_alias="BACKUP_HUB_SESSION_COOKIE")
    cookie_secure: bool = Field(default=True, validation_alias="BACKUP_HUB_COOKIE_SECURE")
    session_ttl_seconds: int = Field(default=900, validation_alias="BACKUP_HUB_SESSION_TTL_SECONDS")
    logo_url: str = Field(default=DEFAULT_LOGO_URL, validation_alias="BACKUP_HUB_LOGO_URL")
    favicon_url: str = Field(default=DEFAULT_FAVICON_URL, validation_alias="BACKUP_HUB_FAVICON_URL")

    postgres_host: str = Field(default="", validation_alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, validation_alias="POSTGRES_PORT")
    postgres_user: str = Field(default="", validation_alias="POSTGRES_USER")
    postgres_password: str = Field(default="", validation_alias="POSTGRES_PASSWORD")
    postgres_databases: str = Field(default="", validation_alias="POSTGRES_DATABASES")

    mysql_host: str = Field(default="", validation_alias="MYSQL_HOST")
    mysql_port: int = Field(default=3306, validation_alias="MYSQL_PORT")
    mysql_user: str = Field(default="", validation_alias="MYSQL_USER")
    mysql_password: str = Field(default="", validation_alias="MYSQL_PASSWORD")
    mysql_databases: str = Field(default="", validation_alias="MYSQL_DATABASES")

    mariadb_host: str = Field(default="", validation_alias="MARIADB_HOST")
    mariadb_port: int = Field(default=3306, validation_alias="MARIADB_PORT")
    mariadb_user: str = Field(default="", validation_alias="MARIADB_USER")
    mariadb_password: str = Field(default="", validation_alias="MARIADB_PASSWORD")
    mariadb_databases: str = Field(default="", validation_alias="MARIADB_DATABASES")

    @field_validator("logo_url")
    @classmethod
    def default_logo_url_when_blank(cls, value: str) -> str:
        return value.strip() or DEFAULT_LOGO_URL

    @field_validator("favicon_url")
    @classmethod
    def default_favicon_url_when_blank(cls, value: str) -> str:
        return value.strip() or DEFAULT_FAVICON_URL


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings: Settings = get_settings()


DatabaseKind = Literal["postgres", "mysql", "mariadb"]


def split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]
