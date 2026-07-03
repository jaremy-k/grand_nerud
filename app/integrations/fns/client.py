import httpx

from app.config import settings
from app.integrations.exceptions import IntegrationError, IntegrationHTTPError
from app.integrations.fns.parser import parse_company_data
from app.logger import logger

PROVIDER = "FNS"


class FnsClient:
    def __init__(self, http_client: httpx.AsyncClient):
        self._http = http_client

    async def get_company_by_inn(self, inn: int | str) -> dict:
        try:
            response = await self._http.get(
                settings.API_FNS_URL,
                params={"req": inn, "key": settings.API_FNS_KEY},
            )
            logger.info("FNS response: status=%s", response.status_code)

            if response.is_error:
                raise IntegrationHTTPError(PROVIDER, response.status_code, response.text)

            return parse_company_data(response.json())
        except IntegrationError:
            raise
        except httpx.HTTPError as e:
            logger.error("FNS request failed: %s", e, exc_info=True)
            raise IntegrationError("Не удалось выполнить запрос к ФНС", PROVIDER) from e
        except ValueError as e:
            logger.error("FNS invalid JSON: %s", e, exc_info=True)
            raise IntegrationError("Некорректный ответ ФНС", PROVIDER) from e
