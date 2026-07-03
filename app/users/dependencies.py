from bson import ObjectId
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.config import settings
from app.exceptions import IncorrectTokenFormatException, TokenAbsentException, UserIsNotPresentException
from app.users.dao import UsersDAO
from app.users.shemas import SUsersGet

bearer_scheme = HTTPBearer(auto_error=False)


def get_token(credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme)) -> str:
    if not credentials or not credentials.credentials:
        raise TokenAbsentException
    return credentials.credentials


async def get_current_user(token: str = Depends(get_token)) -> SUsersGet:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        raise IncorrectTokenFormatException

    user_id: str | None = payload.get("sub")
    if not user_id:
        raise UserIsNotPresentException

    user_dict = await UsersDAO.find_one_or_none(_id=ObjectId(user_id))
    if not user_dict or user_dict.get("deletedAt"):
        raise UserIsNotPresentException

    return SUsersGet.model_validate(user_dict)


async def get_current_admin_user(current_user: SUsersGet = Depends(get_current_user)) -> SUsersGet:
    if not current_user.admin:
        raise UserIsNotPresentException
    return current_user
