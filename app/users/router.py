from fastapi import APIRouter, Depends

from app.exceptions import UserAlreadyExistsException, IncorrectEmailOrPasswordException
from app.users.auth import get_password_hash, authenticate_user, create_access_token
from app.users.dao import UsersDAO
from app.users.dependencies import get_current_user, get_current_admin_user
from app.users.shemas import SUsersAuth, SUsersGetResponse

router = APIRouter(
    prefix="/auth",
    tags=["Auth & Пользователи"],
)


@router.post("/register")
async def register_user(data: SUsersAuth):
    existing_user = await UsersDAO.find_one_or_none(email=data.email)
    if existing_user:
        raise UserAlreadyExistsException

    hashed_password = get_password_hash(data.password)
    await UsersDAO.add({"email": data.email, "hashed_password": hashed_password})


@router.post("/login")
async def login_user(user_data: SUsersAuth):
    user = await authenticate_user(user_data.email, user_data.password)
    if not user:
        raise IncorrectEmailOrPasswordException
    access_token = create_access_token({"sub": str(user.id)})
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me")
async def read_users_me(current_user: SUsersGetResponse = Depends(get_current_user)) -> SUsersGetResponse:
    return current_user


@router.get("/all")
async def read_users_all(
        current_user: SUsersGet = Depends(get_current_admin_user),
) -> list[SUsersGetResponse]:
    return await UsersDAO.find_all()
