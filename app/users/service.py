from bson import ObjectId
from fastapi import HTTPException, status

from app.core.base_entity_service import BaseEntityService
from app.deals.dao import DealsDAO
from app.users.auth import get_password_hash
from app.users.dao import UsersDAO
from app.users.shemas import SUsersUpdate


class UsersService(BaseEntityService):
    dao = UsersDAO
    not_found_detail = "Пользователь не найден"
    conflict_detail = "Невозможно удалить пользователя — имеются связанные сделки"

    @classmethod
    async def list_users(cls, include_deleted: bool = False) -> list[dict]:
        query = {}
        if not include_deleted:
            query["deletedAt"] = None
        return await cls.dao.find_all(**query)

    @classmethod
    async def update(cls, user_id: str, data: SUsersUpdate, is_admin: bool = False) -> dict:
        existing = await cls.dao.find_one_or_none(_id=ObjectId(user_id))
        if not existing:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=cls.not_found_detail)

        if existing.get("deletedAt"):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=cls.not_found_detail)

        update_data = data.model_dump(exclude_none=True)

        if "admin" in update_data and not is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Недостаточно прав для изменения роли администратора",
            )
        if not is_admin:
            update_data.pop("admin", None)

        if "password" in update_data:
            update_data["hashed_password"] = get_password_hash(update_data.pop("password"))

        if "email" in update_data and not await cls.dao.is_unique(
                field_name="email",
                value=update_data["email"],
                exclude_id=user_id,
                case_sensitive=False,
                trim_spaces=True,
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Пользователь с таким email уже существует",
            )

        if not update_data:
            return existing

        result = await cls.dao.update_by_id(object_id=user_id, update_data=update_data)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Не удалось обновить пользователя",
            )
        return result

    @classmethod
    async def has_dependencies(cls, user_id: str) -> bool:
        count = await DealsDAO.count({"userId": ObjectId(user_id), "deletedAt": None})
        return count > 0
