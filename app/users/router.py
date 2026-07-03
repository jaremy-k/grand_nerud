from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status

from app.exceptions import UserAlreadyExistsException, IncorrectEmailOrPasswordException
from app.logger import logger
from app.users.auth import get_password_hash, authenticate_user, create_access_token
from app.users.dao import UsersDAO
from app.users.dependencies import get_current_user, get_current_admin_user
from app.users.service import UsersService
from app.users.shemas import SUsersAuth, SUsersGet, SUsersGetResponse, SUsersUpdate

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
        includeDeleted: bool = Query(False),
) -> list[SUsersGetResponse]:
    return await UsersService.list_users(include_deleted=includeDeleted)


@router.get("/users/{id}", response_model=SUsersGetResponse, summary="Получить пользователя по ID")
async def get_user(
        id: str,
        current_user: SUsersGet = Depends(get_current_user),
) -> SUsersGetResponse:
    if not current_user.admin and str(current_user.id) != id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")
    return await UsersService.get_by_id(id)


@router.patch("/users/{id}", response_model=SUsersGetResponse, summary="Обновить пользователя по ID")
async def update_user(
        id: str,
        data: SUsersUpdate,
        background_tasks: BackgroundTasks,
        current_user: SUsersGet = Depends(get_current_user),
) -> SUsersGetResponse:
    if not current_user.admin and str(current_user.id) != id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")

    result = await UsersService.update(id, data, is_admin=bool(current_user.admin))
    background_tasks.add_task(
        logger.info, "User updated: id=%s", id,
        extra={"user_id": id, "action": "user_update"},
    )
    return result


@router.delete("/users/{id}", response_model=Optional[SUsersGetResponse], summary="Мягкое удаление пользователя")
async def safe_delete_user(
        id: str,
        background_tasks: BackgroundTasks,
        current_user: SUsersGet = Depends(get_current_admin_user),
        check_dependencies: bool = True,
):
    if str(current_user.id) == id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Нельзя удалить собственный аккаунт",
        )

    result = await UsersService.soft_delete(
        id,
        check_dependencies=check_dependencies,
        dependency_checker=UsersService.has_dependencies,
    )
    background_tasks.add_task(
        logger.info, "User safely deleted: id=%s", id,
        extra={"user_id": id, "action": "safe_delete"},
    )
    return result
