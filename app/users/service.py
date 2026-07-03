from bson import ObjectId

from app.core.base_entity_service import BaseEntityService
from app.deals.repository import deals_repository
from app.exceptions import ConflictError, ForbiddenError, InternalError, NotFoundError, UserAlreadyExistsError
from app.users.auth import get_password_hash
from app.users.repository import users_repository
from app.users.shemas import SUsersCreate, SUsersUpdate


class UsersService(BaseEntityService):
    repository = users_repository
    not_found_detail = "Пользователь не найден"
    conflict_detail = "Невозможно удалить пользователя — имеются связанные сделки"

    @classmethod
    async def list_users(cls, include_deleted: bool = False) -> list[dict]:
        query = {}
        if not include_deleted:
            query["deletedAt"] = None
        return await cls.repository.find_many(**query)

    @classmethod
    async def create(cls, data: SUsersCreate) -> dict:
        existing = await cls.repository.find_one(email=data.email)
        if existing:
            raise UserAlreadyExistsError()

        document = {
            "email": data.email,
            "hashed_password": get_password_hash(data.password),
            "admin": data.admin or False,
            "name": data.name,
            "lastName": data.lastName,
            "fatherName": data.fatherName,
            "profit": data.profit,
        }
        document = {key: value for key, value in document.items() if value is not None}

        result = await cls.repository.create(document)
        if not result:
            raise InternalError("Не удалось создать пользователя")
        return result

    @classmethod
    async def update(cls, user_id: str, data: SUsersUpdate, is_admin: bool = False) -> dict:
        existing = await cls.repository.find_one(_id=ObjectId(user_id))
        if not existing:
            raise NotFoundError(cls.not_found_detail)

        if existing.get("deletedAt"):
            raise NotFoundError(cls.not_found_detail)

        update_data = data.model_dump(exclude_none=True)

        if "admin" in update_data and not is_admin:
            raise ForbiddenError("Недостаточно прав для изменения роли администратора")
        if not is_admin:
            update_data.pop("admin", None)

        if "password" in update_data:
            update_data["hashed_password"] = get_password_hash(update_data.pop("password"))

        if "email" in update_data and not await cls.repository.is_unique(
                field_name="email",
                value=update_data["email"],
                exclude_id=user_id,
                case_sensitive=False,
                trim_spaces=True,
        ):
            raise ConflictError("Пользователь с таким email уже существует")

        if not update_data:
            return existing

        result = await cls.repository.update_by_id(object_id=user_id, update_data=update_data)
        if not result:
            raise InternalError("Не удалось обновить пользователя")
        return result

    @classmethod
    async def has_dependencies(cls, user_id: str) -> bool:
        count = await deals_repository.count({"userId": ObjectId(user_id), "deletedAt": None})
        return count > 0
