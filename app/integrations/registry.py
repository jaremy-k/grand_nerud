from app.integrations.fns.client import FnsClient
from app.integrations.http import close_http_client, get_http_client, init_http_client
from app.integrations.s3.client import S3StorageClient

_fns_client: FnsClient | None = None
_s3_client: S3StorageClient | None = None


async def init_integrations() -> None:
    global _fns_client, _s3_client
    await init_http_client()
    _fns_client = FnsClient(get_http_client())
    _s3_client = S3StorageClient()


async def close_integrations() -> None:
    global _fns_client, _s3_client
    _fns_client = None
    _s3_client = None
    await close_http_client()


def get_fns_client() -> FnsClient:
    if _fns_client is None:
        raise RuntimeError("FNS client is not initialized")
    return _fns_client


def get_s3_client() -> S3StorageClient:
    if _s3_client is None:
        raise RuntimeError("S3 client is not initialized")
    return _s3_client
