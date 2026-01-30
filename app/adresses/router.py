from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from starlette import status

from app.adresses.dao import AdressesDAO
from app.adresses.shemas import SAdresses, SAdressesAdd
from app.logger import logger
from app.users.dependencies import get_current_admin_user

router = APIRouter(
    prefix="/adresses",
    tags=["Адреса"]
)


@router.get("/{id}", response_model=SAdresses, summary="Получить материал по ID")
async def get_material(id: str) -> SAdresses:
    result = await AdressesDAO.find_one_or_none(_id=ObjectId(id))
    return result


@router.get("", response_model=list[SAdresses], summary="Получить список материалов")
async def get_materials(data: SAdresses = Depends()) -> list[
    SAdresses]:
    result = await AdressesDAO.find_all(**data.model_dump(exclude_none=True))
    return result


@router.post(
    "",
    response_model=SAdresses,
    summary="Добавить материал",
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_201_CREATED: {"description": "Материал успешно создан"},
        status.HTTP_409_CONFLICT: {"description": "Материал с таким именем уже существует"},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"description": "Ошибка сервера"}
    }
)
async def add_adress(data: SAdressesAdd):
    """
    Добавление нового материала.

    Проверяет уникальность имени материала перед добавлением.
    """
    try:
        # Проверка уникальности name без учёта регистра и с обрезкой пробелов
        if not await AdressesDAO.is_unique(
                field_name="name",
                value=data.name,
                case_sensitive=False,
                trim_spaces=True
        ):
            raise HTTPException(
                status_code=409,
                detail="Материал с таким именем уже существует"
            )

        # Создание материала
        material_data = data.model_dump(exclude_none=True)
        result = await AdressesDAO.add(document=material_data)

        if not result:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Не удалось создать материал"
            )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при создании материала: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Произошла ошибка при создании материала"
        )


@router.patch(
    "/{id}",
    response_model=SAdresses,
    summary="Обновить материал по ID",
    responses={
        200: {"description": "Материал успешно обновлен"},
        400: {"description": "Невалидные данные или имя уже существует"},
        404: {"description": "Материал не найден"},
        500: {"description": "Внутренняя ошибка сервера"}
    }
)
async def update_material(
        id: str,
        data: SAdressesAdd,
        background_tasks: BackgroundTasks
):
    """
    Обновляет материал с проверкой уникальности имени.

    Проверяет:
    - Что материал с указанным ID существует
    - Что новое имя (если передано) не занято другими материалами
    - Обрезает пробелы в имени
    - Не учитывает регистр при проверке уникальности
    """
    try:
        # Проверяем существование материала
        existing_material = await AdressesDAO.find_one_or_none(_id=ObjectId(id))

        if not existing_material:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Материал не найден"
            )

        update_data = data.model_dump(exclude_none=True)

        if "name" in update_data:
            # Проверка на уникальность
            if not await AdressesDAO.is_unique(
                    field_name="name",
                    value=data.name,
                    exclude_id=id,
                    case_sensitive=False,
                    trim_spaces=True
            ):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Материал с таким именем уже существует"
                )

        # Фоновое логирование изменения
        background_tasks.add_task(
            logger.info,
            "Material updated: id=%s, changes=%s",  # Сообщение
            id,  # Первый аргумент
            list(update_data.keys()),  # Второй аргумент
            extra={
                'material_id': id,
                'changes': list(update_data.keys()),
                'action': 'material_update'
            }
        )

        # Выполняем обновление
        result = await AdressesDAO.update_by_id(
            object_id=id,
            update_data=update_data
        )

        if not result:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Не удалось обновить материал"
            )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка обновления материала: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Внутренняя ошибка сервера"
        )


@router.delete(
    "/{id}",
    response_model=Optional[SAdresses],
    summary="Безопасное удаление материала",
    responses={
        status.HTTP_200_OK: {
            "description": "Материал успешно удален",
            "model": SAdresses
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Материал не найден"
        },
        status.HTTP_409_CONFLICT: {
            "description": "Материал имеет связанные зависимости"
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Внутренняя ошибка сервера"
        }
    }
)
async def safe_delete_material(
        id: str,
        background_tasks: BackgroundTasks,
        check_dependencies: bool = True
):
    """
    Безопасное удаление материала с проверками:

    - Проверяет существование материала
    - Проверяет связанные зависимости (если check_dependencies=True)
    - Софт-удаление (помечает как удаленный)
    - Логирование действия

    Параметры:
    - id: ID материала
    - check_dependencies: Проверять ли связанные объекты (по умолчанию True)
    """
    try:
        # Проверяем существование материала
        material = await AdressesDAO.find_one_or_none(_id=ObjectId(id))
        if not material:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Материал не найден"
            )

        # Проверка зависимостей (если требуется)
        if check_dependencies:
            has_dependencies = await check_material_dependencies(id)
            if has_dependencies:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Невозможно удалить материал - имеются связанные объекты"
                )

        # Софт-удаление (помечаем как удаленный)
        result = await AdressesDAO.soft_delete(id)

        if not result:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Не удалось удалить материал"
            )

        # Логирование в фоне
        background_tasks.add_task(
            logger.info,
            "Material safely deleted: id=%s", id,
            extra={
                'material_id': id,
                'action': 'safe_delete',
                'deleted_by': 'system',  # Можно добавить auth пользователя
                'dependencies_checked': check_dependencies
            }
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Safe delete failed: %s", str(e),
            extra={
                'material_id': id,
                'error': str(e),
                'stack_trace': True
            }
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Внутренняя ошибка сервера при удалении"
        )


async def check_material_dependencies(adress_id: str) -> bool:
    """
    Проверяет наличие зависимых объектов у материала

    Возвращает:
    - True если есть зависимости
    - False если зависимостей нет
    """
    # Пример проверки в других коллекциях
    from app.deals.dao import DealsDAO

    # Проверяем, используется ли адрес в сделках (доставка или отгрузка)
    oid = ObjectId(adress_id)
    deals_using_adress = await DealsDAO.count(
        {"$or": [
            {"shippingAddressId": oid},
            {"deliveryAddressId": oid}
        ]}
    )

    # Можно добавить другие проверки (заказы, документы и т.д.)

    return deals_using_adress > 0
