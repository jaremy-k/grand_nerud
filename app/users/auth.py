from datetime import datetime, timedelta

import bcrypt
from jose import jwt
from pydantic import EmailStr

from app.config import settings
from app.users.repository import users_repository
from app.users.shemas import SUsersGet


def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        hashed_password.encode("utf-8"),
    )


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now() + timedelta(days=30)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(
        to_encode, settings.SECRET_KEY, settings.ALGORITHM
    )
    return encoded_jwt


async def authenticate_user(email: EmailStr, password: str):
    user_dict = await users_repository.find_one(email=email)
    if not user_dict or user_dict.get("deletedAt"):
        return None
    user = SUsersGet.model_validate(user_dict)
    if not (user and user.hashed_password and verify_password(password, user.hashed_password)):
        return None
    return user
