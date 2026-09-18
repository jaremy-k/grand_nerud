from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status

from app.companies.service import CompaniesService
from app.companies.shemas import CompanyRole, SCompanies, SCompaniesAdd
from app.logger import logger
from app.users.dependencies import get_current_user

router = APIRouter(
    prefix="/companies",
    tags=["Компании партнеры"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/fns/{inn}", summary="Получить компанию по ИНН из KontragentPro")
async def get_company_info(inn: int):
    return await CompaniesService.fetch_by_inn(inn)


@router.get("/{id}", response_model=SCompanies, summary="Получить компанию по ID")
async def get_company_by_id(id: str) -> SCompanies:
    return await CompaniesService.get_by_id(id)


@router.get("", response_model=list[SCompanies], summary="Получить список компаний")
async def get_companies(
        data: SCompanies = Depends(),
        role: CompanyRole | None = Query(None, description="Роль компании в сделках"),
        includeDeleted: bool = Query(False),
) -> list[SCompanies]:
    return await CompaniesService.list_companies(
        data,
        include_deleted=includeDeleted,
        role=role,
    )


@router.post(
    "",
    response_model=SCompanies,
    summary="Добавить компанию",
    status_code=status.HTTP_201_CREATED,
)
async def add_company(data: SCompaniesAdd):
    return await CompaniesService.create(data)


@router.patch("/{id}", response_model=SCompanies, summary="Обновить компанию по ID")
async def update_company(id: str, data: SCompaniesAdd, background_tasks: BackgroundTasks):
    result = await CompaniesService.update(id, data)
    background_tasks.add_task(
        logger.info, "Company updated: id=%s", id,
        extra={"company_id": id, "action": "company_update"},
    )
    return result


@router.delete("/{id}", response_model=Optional[SCompanies], summary="Мягкое удаление компании")
async def safe_delete_company(
        id: str,
        background_tasks: BackgroundTasks,
        check_dependencies: bool = True,
):
    result = await CompaniesService.soft_delete(
        id,
        check_dependencies=check_dependencies,
        dependency_checker=CompaniesService.has_dependencies,
    )
    background_tasks.add_task(
        logger.info, "Company safely deleted: id=%s", id,
        extra={"company_id": id, "action": "safe_delete"},
    )
    return result
