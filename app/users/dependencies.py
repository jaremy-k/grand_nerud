from bson import ObjectId
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.config import settings
from app.core.object_id import parse_object_id
from app.exceptions import (
    ForbiddenError,
    IncorrectTokenFormatError,
    TokenAbsentError,
    UserNotFoundError,
)
from app.users.repository import users_repository
from app.users.shemas import SUsersGet

bearer_scheme = HTTPBearer(auto_error=False)


def get_token(credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme)) -> str:
    if not credentials or not credentials.credentials:
        raise TokenAbsentError()
    return credentials.credentials


async def get_current_user(token: str = Depends(get_token)) -> SUsersGet:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        raise IncorrectTokenFormatError()

    user_id: str | None = payload.get("sub")
    if not user_id:
        raise UserNotFoundError()

    user_dict = await users_repository.find_one(_id=parse_object_id(user_id, "user_id"))
    if not user_dict or user_dict.get("deletedAt"):
        raise UserNotFoundError()

    return SUsersGet.model_validate(user_dict)


async def get_current_admin_user(current_user: SUsersGet = Depends(get_current_user)) -> SUsersGet:
    if not current_user.admin:
        raise ForbiddenError()
    return current_user


async def get_current_privileged_user(current_user: SUsersGet = Depends(get_current_user)) -> SUsersGet:
    if not current_user.is_privileged:
        raise ForbiddenError()
    return current_user


async def get_current_formula_access_user(current_user: SUsersGet = Depends(get_current_user)) -> SUsersGet:
    if current_user.manager and not current_user.admin:
        raise ForbiddenError("Доступ к формулам запрещён")
    return current_user
