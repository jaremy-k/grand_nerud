from app.integrations.http import close_http_client, get_http_client, init_http_client
from app.integrations.kontragentpro.client import KontragentProClient
from app.integrations.s3.client import S3StorageClient

_kontragentpro_client: KontragentProClient | None = None
_s3_client: S3StorageClient | None = None


async def init_integrations() -> None:
    global _kontragentpro_client, _s3_client
    await init_http_client()
    _kontragentpro_client = KontragentProClient(get_http_client())
    _s3_client = None


async def close_integrations() -> None:
    global _kontragentpro_client, _s3_client
    _kontragentpro_client = None
    _s3_client = None
    await close_http_client()


def get_kontragentpro_client() -> KontragentProClient:
    if _kontragentpro_client is None:
        raise RuntimeError("KontragentPro client is not initialized")
    return _kontragentpro_client


def get_s3_client() -> S3StorageClient:
    from app.config import settings

    global _s3_client
    if not settings.is_s3_enabled:
        raise RuntimeError("S3 is not configured")
    if _s3_client is None:
        _s3_client = S3StorageClient()
    return _s3_client
