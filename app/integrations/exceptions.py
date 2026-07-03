class IntegrationError(Exception):
    def __init__(self, message: str, provider: str):
        self.message = message
        self.provider = provider
        super().__init__(message)


class IntegrationHTTPError(IntegrationError):
    def __init__(self, provider: str, status_code: int, body: str = ""):
        self.status_code = status_code
        self.body = body
        super().__init__(
            f"{provider} вернул HTTP {status_code}",
            provider,
        )
