import json
from datetime import datetime, date
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from fastapi.responses import JSONResponse
from starlette import status

from app.deals.dao import DealsDAO
from app.deals.shemas import SDeals, SDealsAdd, SDealsWithRelations, PaginatedResponse, PaginationParams
from app.logger import logger
from app.users.dependencies import get_current_user

router = APIRouter(
    prefix="/deals",
    tags=["Сделки"]
)


class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, ObjectId):
            return str(obj)
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        return super().default(obj)


# @router.get("/{id}", response_model=SDeals, summary="Получить материал по ID")
async def get_deal(id: str, user=Depends(get_current_user)) -> SDeals:
    result = await DealsDAO.find_one_or_none(_id=ObjectId(id))
    return result


@router.get("", response_model=PaginatedResponse, summary="Получить список материалов")
async def get_deals(
        pagination: PaginationParams = Depends(),
        sortBy: Optional[str] = Query(None, description="Поле для сортировки"),
        sortOrder: Optional[str] = Query("asc", regex="^(asc|desc)$", description="Порядок сортировки"),
        includeRelations: bool = Query(False, description="Включать связанные объекты"),  # Новый параметр
        includeDeleted: bool = Query(False, description="(deletedAt = null)"),
        data: SDeals = Depends(),
        user=Depends(get_current_user)
) -> PaginatedResponse:
    if not hasattr(user, 'admin') or user.admin == False:
        logger.info('is_admin')
        data.userId = ObjectId(user.id)
    filter_data = data.model_dump(exclude_none=True)

    if not includeDeleted:
        filter_data["deletedAt"] = None

    # Подготавливаем параметры сортировки
    sort = None
    if sortBy:
        order = 1 if sortOrder == "asc" else -1
        sort = [(sortBy, order)]

    # Используем пагинированный запрос с опциональными связями
    result = await DealsDAO.find_paginated1(
        filter_by=filter_data,
        skip=pagination.skip,
        limit=pagination.limit,
        sort=sort,
        include_relations=includeRelations  # Передаем параметр
    )

    return result


@router.get("/admin/get", summary="Получить список сделок со связанными объектами")
async def get_deals_for_admins(data: SDeals = Depends()):
    # if not hasattr(user, 'admin') or user.admin == False:
    #     raise HTTPException(status_code=403, detail="Доступ закрыт")

    pipeline = [
        {"$lookup": {
            "from": "services",
            "localField": "serviceId",
            "foreignField": "_id",
            "as": "service"
        }},
        {"$lookup": {
            "from": "customers",
            "localField": "customerId",
            "foreignField": "_id",
            "as": "customer"
        }},
        {"$lookup": {
            "from": "stages",
            "localField": "stageId",
            "foreignField": "_id",
            "as": "stage"
        }},
        {"$lookup": {
            "from": "materials",
            "localField": "materialId",
            "foreignField": "_id",
            "as": "material"
        }},
        {"$lookup": {
            "from": "addresses",
            "localField": "shippingAddressId",
            "foreignField": "_id",
            "as": "shipping_address"
        }},
        {"$lookup": {
            "from": "addresses",
            "localField": "deliveryAddressId",
            "foreignField": "_id",
            "as": "delivery_address"
        }},
        {"$lookup": {
            "from": "users",
            "localField": "userId",
            "foreignField": "_id",
            "as": "user"
        }},
        {"$addFields": {
            "service": {"$arrayElemAt": ["$service", 0]},
            "customer": {"$arrayElemAt": ["$customer", 0]},
            "stage": {"$arrayElemAt": ["$stage", 0]},
            "material": {"$arrayElemAt": ["$material", 0]},
            "shipping_address": {"$arrayElemAt": ["$shipping_address", 0]},
            "delivery_address": {"$arrayElemAt": ["$delivery_address", 0]},
            "user": {"$arrayElemAt": ["$user", 0]},
        }}
    ]

    result = await DealsDAO.aggregate(pipeline)
    # Сериализация ObjectId и datetime для JSON (как в get_deal_with_relations)
    deal_list = [json.loads(json.dumps(doc, cls=CustomJSONEncoder, default=str)) for doc in result]
    return JSONResponse(content=deal_list)


@router.get("/{id}",
            response_model=SDealsWithRelations,
            summary="Получить сделку с связанными объектами")
async def get_deal_with_relations(id: str):
    pipeline = [
        {"$match": {"_id": ObjectId(id)}},
        {"$lookup": {
            "from": "services",
            "localField": "serviceId",
            "foreignField": "_id",
            "as": "service"
        }},
        {"$lookup": {
            "from": "customers",
            "localField": "customerId",
            "foreignField": "_id",
            "as": "customer"
        }},
        {"$lookup": {
            "from": "stages",
            "localField": "stageId",
            "foreignField": "_id",
            "as": "stage"
        }},
        {"$lookup": {
            "from": "materials",
            "localField": "materialId",
            "foreignField": "_id",
            "as": "material"
        }},
        {"$lookup": {
            "from": "addresses",
            "localField": "shippingAddressId",
            "foreignField": "_id",
            "as": "shipping_address"
        }},
        {"$lookup": {
            "from": "addresses",
            "localField": "deliveryAddressId",
            "foreignField": "_id",
            "as": "delivery_address"
        }},
        {"$lookup": {
            "from": "users",
            "localField": "userId",
            "foreignField": "_id",
            "as": "user"
        }},
        {"$addFields": {
            "service": {"$arrayElemAt": ["$service", 0]},
            "customer": {"$arrayElemAt": ["$customer", 0]},
            "stage": {"$arrayElemAt": ["$stage", 0]},
            "material": {"$arrayElemAt": ["$material", 0]},
            "shipping_address": {"$arrayElemAt": ["$shipping_address", 0]},
            "delivery_address": {"$arrayElemAt": ["$delivery_address", 0]},
            "user": {"$arrayElemAt": ["$user", 0]},
        }}
    ]

    result = await DealsDAO.aggregate(pipeline)
    if not result:
        raise HTTPException(status_code=404, detail="Deal not found")

    json_str = json.dumps(result[0], cls=CustomJSONEncoder, default=str)
    deal_data = json.loads(json_str)

    return JSONResponse(content=deal_data)


@router.post(
    "",
    response_model=SDeals,
    summary="Добавить",
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_201_CREATED: {"description": "Объект успешно создан"},
        status.HTTP_409_CONFLICT: {"description": "Объект с таким именем уже существует"},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"description": "Ошибка сервера"}
    }
)
async def add_deal(data: SDealsAdd, user=Depends(get_current_user)):
    """
    Добавление нового материала.

    Проверяет уникальность имени материала перед добавлением.
    """
    try:
        # Создание материала
        data.userId = ObjectId(user.id)
        data.createdAt = datetime.now()
        material_data = data.model_dump(exclude_none=True)
        result = await DealsDAO.add(document=material_data)

        if not result:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Не удалось создать объект"
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
    response_model=SDeals,
    summary="Обновить материал по ID",
    responses={
        200: {"description": "Материал успешно обновлен"},
        400: {"description": "Невалидные данные или имя уже существует"},
        404: {"description": "Материал не найден"},
        500: {"description": "Внутренняя ошибка сервера"}
    }
)
async def update_deal(
        id: str,
        data: SDealsAdd,
        background_tasks: BackgroundTasks,
        user=Depends(get_current_user)
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
        existing_material = await DealsDAO.find_one_or_none(_id=ObjectId(id))

        if not existing_material:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Объект не найден"
            )

        update_data = data.model_dump(exclude_none=True)

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
        result = await DealsDAO.update_by_id(
            object_id=id,
            update_data=update_data
        )

        if not result:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Не удалось обновить объект"
            )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка обновления объекта: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Внутренняя ошибка сервера"
        )


@router.delete(
    "/{id}",
    response_model=Optional[SDeals],
    summary="Безопасное удаление объекта",
    responses={
        status.HTTP_200_OK: {
            "description": "Материал успешно удален",
            "model": SDeals
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
async def safe_delete_deal(
        id: str,
        background_tasks: BackgroundTasks,
        check_dependencies: bool = True,
        user=Depends(get_current_user)
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
        material = await DealsDAO.find_one_or_none(_id=ObjectId(id))
        if not material:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Объект не найден"
            )

        # Проверка зависимостей (если требуется)
        if check_dependencies:
            has_dependencies = await check_material_dependencies(id)
            if has_dependencies:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Невозможно удалить обхект - имеются связанные объекты"
                )

        # Софт-удаление (помечаем как удаленный)
        result = await DealsDAO.update_by_id(id, {"deletedAt": datetime.now()})

        if not result:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Не удалось удалить объект"
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

    # Проверяем, используется ли материал в продуктах
    # deals_using_company = await DealsDAO.count(
    #     {"customerId": ObjectId(adress_id)}
    # )

    # Можно добавить другие проверки (заказы, документы и т.д.)

    return False
