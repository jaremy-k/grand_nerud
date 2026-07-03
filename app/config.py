from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    MODE: Literal["DEV", "TEST", "PROD", "POEZD"] = "DEV"
    LOG_LEVEL: Literal["DEBUG", "INFO"] = "INFO"

    SECRET_KEY: str
    ALGORITHM: str = "HS256"

    MONGO_HOST: str = "mongo"
    MONGO_PORT: int = 27017
    MONGO_INITDB_ROOT_USERNAME: str
    MONGO_INITDB_ROOT_PASSWORD: str
    MONGO_INITDB_DATABASE: str

    S3_ENDPOINT: str | None = None
    S3_BUCKET: str | None = None
    S3_ACCESS_KEY: str | None = None
    S3_SECRET_KEY: str | None = None

    API_FNS_URL: str
    API_FNS_KEY: str

    CORS_ORIGINS: str = "*"
    ALLOW_REGISTRATION: bool = True

    @property
    def MONGO_URL(self) -> str:
        return (
            f"mongodb://{self.MONGO_INITDB_ROOT_USERNAME}:"
            f"{self.MONGO_INITDB_ROOT_PASSWORD}@{self.MONGO_HOST}:"
            f"{self.MONGO_PORT}"
        )

    @property
    def cors_origins(self) -> list[str]:
        if self.CORS_ORIGINS.strip() == "*":
            return ["*"]
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def is_s3_enabled(self) -> bool:
        return bool(self.S3_ENDPOINT and self.S3_BUCKET and self.S3_ACCESS_KEY and self.S3_SECRET_KEY)

    model_config = SettingsConfigDict(
        env_file=(".env", ".env_prod"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
