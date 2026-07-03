class AppError(Exception):
    status_code: int = 500
    default_detail: str = "Внутренняя ошибка сервера"

    def __init__(self, detail: str | None = None):
        self.detail = detail or self.default_detail
        super().__init__(self.detail)


class NotFoundError(AppError):
    status_code = 404
    default_detail = "Объект не найден"


class ConflictError(AppError):
    status_code = 409
    default_detail = "Конфликт данных"


class ValidationError(AppError):
    status_code = 422
    default_detail = "Невалидные данные"


class UnauthorizedError(AppError):
    status_code = 401
    default_detail = "Требуется авторизация"


class ForbiddenError(AppError):
    status_code = 403
    default_detail = "Доступ запрещён"


class ExternalServiceError(AppError):
    status_code = 502
    default_detail = "Ошибка внешнего сервиса"


class InternalError(AppError):
    status_code = 500
    default_detail = "Внутренняя ошибка сервера"


class UserAlreadyExistsError(ConflictError):
    default_detail = "Пользователь уже существует"


class IncorrectEmailOrPasswordError(UnauthorizedError):
    default_detail = "Неверная почта или пароль"


class TokenAbsentError(UnauthorizedError):
    default_detail = "Токен отсутствует. Передайте заголовок Authorization: Bearer <token>"


class IncorrectTokenFormatError(UnauthorizedError):
    default_detail = "Неверный формат токена"


class UserNotFoundError(UnauthorizedError):
    default_detail = "Пользователь не найден"


class RegistrationDisabledError(ForbiddenError):
    default_detail = "Регистрация отключена"
