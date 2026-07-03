from fastapi import APIRouter, Depends

from app.config import settings
from app.exceptions import (
    IncorrectEmailOrPasswordError,
    RegistrationDisabledError,
    UserAlreadyExistsError,
)
from app.users.auth import authenticate_user, create_access_token, get_password_hash
from app.users.dependencies import get_current_admin_user, get_current_user
from app.users.repository import users_repository
from app.users.service import UsersService
from app.users.shemas import SUsersAuth, SUsersCreate, SUsersGet, SUsersGetResponse, SUsersUpdate

router = APIRouter(
    prefix="/auth",
    tags=["Auth & Пользователи"],
)


@router.post("/register", status_code=201)
async def register_user(data: SUsersAuth):
    if not settings.ALLOW_REGISTRATION:
        raise RegistrationDisabledError()

    existing_user = await users_repository.find_one(email=data.email)
    if existing_user:
        raise UserAlreadyExistsError()

    hashed_password = get_password_hash(data.password)
    await users_repository.create({"email": data.email, "hashed_password": hashed_password, "admin": False})
    return {"success": True, "message": "Пользователь зарегистрирован"}


@router.post("/login")
async def login_user(user_data: SUsersAuth):
    user = await authenticate_user(user_data.email, user_data.password)
    if not user:
        raise IncorrectEmailOrPasswordError()
    access_token = create_access_token({"sub": str(user.id)})
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me")
async def read_users_me(current_user: SUsersGetResponse = Depends(get_current_user)) -> SUsersGetResponse:
    return current_user


@router.get("/all")
async def read_users_all(
        current_user: SUsersGet = Depends(get_current_admin_user),
) -> list[SUsersGetResponse]:
    return await users_repository.find_many(deletedAt=None)


@router.post("/users", response_model=SUsersGetResponse, status_code=201)
async def create_user(
        data: SUsersCreate,
        _current_user: SUsersGet = Depends(get_current_admin_user),
) -> SUsersGetResponse:
    return await UsersService.create(data)


@router.patch("/users/{user_id}", response_model=SUsersGetResponse)
async def update_user(
        user_id: str,
        data: SUsersUpdate,
        _current_user: SUsersGet = Depends(get_current_admin_user),
) -> SUsersGetResponse:
    return await UsersService.update(user_id, data, is_admin=True)
