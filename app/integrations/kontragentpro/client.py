import httpx

from app.config import settings
from app.integrations.exceptions import IntegrationError, IntegrationHTTPError
from app.integrations.kontragentpro.parser import parse_company_data
from app.logger import logger

PROVIDER = "KontragentPro"


class KontragentProClient:
    def __init__(self, http_client: httpx.AsyncClient):
        self._http = http_client

    async def get_company_by_inn(self, inn: int | str) -> dict:
        inn_value = str(inn).strip()
        url = f"{settings.API_KONTRAGENTPRO_URL.rstrip('/')}/companies/{inn_value}"
        headers = self._auth_headers()

        try:
            response = await self._http.get(url, headers=headers or None)
            logger.info("KontragentPro response: status=%s inn=%s", response.status_code, inn_value)

            if response.is_error:
                raise IntegrationHTTPError(
                    PROVIDER,
                    response.status_code,
                    self._error_message(response),
                )

            payload = response.json()
            if not isinstance(payload, dict):
                raise IntegrationError("Некорректный ответ KontragentPro", PROVIDER)
            return parse_company_data(payload)
        except IntegrationError:
            raise
        except httpx.HTTPError as e:
            logger.error("KontragentPro request failed: %s", e, exc_info=True)
            raise IntegrationError("Не удалось выполнить запрос к KontragentPro", PROVIDER) from e
        except ValueError as e:
            logger.error("KontragentPro invalid JSON: %s", e, exc_info=True)
            raise IntegrationError("Некорректный ответ KontragentPro", PROVIDER) from e

    @staticmethod
    def _auth_headers() -> dict[str, str]:
        key = (settings.API_KONTRAGENTPRO_KEY or "").strip()
        if not key:
            return {}
        return {
            "Authorization": f"Bearer {key}",
            "X-API-Key": key,
        }

    @staticmethod
    def _error_message(response: httpx.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            return response.text

        error = payload.get("error") if isinstance(payload, dict) else None
        if isinstance(error, dict):
            message = error.get("message")
            if message:
                return str(message)
        if isinstance(payload, dict) and payload.get("message"):
            return str(payload["message"])
        return response.text
