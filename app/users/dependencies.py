from bson import ObjectId
from fastapi import Request, Depends

from jose import jwt, JWTError

from app.config import settings
from app.exceptions import TokenAbsentException, IncorrectTokenFormatException, UserIsNotPresentException
from app.logger import logger
from app.users.dao import UsersDAO
from app.users.shemas import SUsersGet


def get_token(request: Request):
    token = request.headers.get("x-user-id")
    # token = request.cookies.get("tg_news_bot_access_token ")
    if not token:
        raise TokenAbsentException
    return token


async def get_current_user(token: str = Depends(get_token)):
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, settings.ALGORITHM
        )
    except JWTError:
        raise IncorrectTokenFormatException
    user_id: str = payload.get("sub")
    logger.info(f"user_id: {user_id}")
    if not user_id:
        raise UserIsNotPresentException
    user_dict = await UsersDAO.find_one_or_none(_id=ObjectId(user_id))
    user = SUsersGet.model_validate(user_dict)
    if not user:
        raise UserIsNotPresentException
    return user


async def get_current_admin_user(current_user=Depends(get_current_user)):
    if not current_user.admin:
        raise UserIsNotPresentException
    return current_user
