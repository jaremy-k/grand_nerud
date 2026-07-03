from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    MODE: Literal["DEV", "TEST", "PROD", "POEZD"]
    LOG_LEVEL: Literal["DEBUG", "INFO"]

    SECRET_KEY: str
    ALGORITHM: str

    S3_ENDPOINT: str
    S3_BUCKET: str
    S3_ACCESS_KEY: str
    S3_SECRET_KEY: str
    S3_KMS_KEY_ID: str

    MONGO_INITDB_ROOT_USERNAME: str
    MONGO_INITDB_ROOT_PASSWORD: str
    MONGO_INITDB_DATABASE: str

    API_FNS_URL: str
    API_FNS_KEY: str

    @property
    def MONGO_URL(self):
        return (
            f"mongodb://{self.MONGO_INITDB_ROOT_USERNAME}:"
            f"{self.MONGO_INITDB_ROOT_PASSWORD}@mongo:27017"
        )

    model_config = SettingsConfigDict(env_file=".env_prod")


settings = Settings()
