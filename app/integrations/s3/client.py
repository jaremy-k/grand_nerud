from contextlib import asynccontextmanager
from typing import AsyncIterator

import aioboto3
from botocore.exceptions import BotoCoreError, ClientError

from app.config import settings
from app.integrations.exceptions import IntegrationError
from app.logger import logger

PROVIDER = "S3"


class S3StorageClient:
    def __init__(self):
        self._session = aioboto3.Session()

    @asynccontextmanager
    async def _client(self) -> AsyncIterator:
        async with self._session.client(
                "s3",
                endpoint_url=settings.S3_ENDPOINT,
                aws_access_key_id=settings.S3_ACCESS_KEY,
                aws_secret_access_key=settings.S3_SECRET_KEY,
        ) as client:
            yield client

    async def upload(
            self,
            key: str,
            data: bytes,
            content_type: str = "application/octet-stream",
    ) -> str:
        try:
            async with self._client() as client:
                await client.put_object(
                    Bucket=settings.S3_BUCKET,
                    Key=key,
                    Body=data,
                    ContentType=content_type,
                )
            return key
        except (ClientError, BotoCoreError) as e:
            logger.error("S3 upload failed: key=%s error=%s", key, e, exc_info=True)
            raise IntegrationError(f"Не удалось загрузить файл: {key}", PROVIDER) from e

    async def download(self, key: str) -> bytes:
        try:
            async with self._client() as client:
                response = await client.get_object(Bucket=settings.S3_BUCKET, Key=key)
                return await response["Body"].read()
        except (ClientError, BotoCoreError) as e:
            logger.error("S3 download failed: key=%s error=%s", key, e, exc_info=True)
            raise IntegrationError(f"Не удалось скачать файл: {key}", PROVIDER) from e

    async def delete(self, key: str) -> None:
        try:
            async with self._client() as client:
                await client.delete_object(Bucket=settings.S3_BUCKET, Key=key)
        except (ClientError, BotoCoreError) as e:
            logger.error("S3 delete failed: key=%s error=%s", key, e, exc_info=True)
            raise IntegrationError(f"Не удалось удалить файл: {key}", PROVIDER) from e
