from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Query, UploadFile, status

from app.companies.service import CompaniesService
from app.adresses.shemas import MoscowAdministrativeDistrict
from app.companies.shemas import (
    CompanyRole,
    SCompanies,
    SCompaniesAdd,
    SCompanyImportResult,
    SCompaniesWithDetails,
)
from app.exceptions import ValidationError
from app.logger import logger
from app.users.dependencies import get_current_user
from app.users.shemas import SUsersGet

router = APIRouter(
    prefix="/companies",
    tags=["Компании партнеры"],
    dependencies=[Depends(get_current_user)],
)

MAX_EXCEL_FILE_SIZE = 10 * 1024 * 1024


@router.get("/fns/{inn}", summary="Получить компанию по ИНН из KontragentPro")
async def get_company_info(inn: int):
    return await CompaniesService.fetch_by_inn(inn)


@router.post("/import", response_model=SCompanyImportResult, summary="Импортировать компании из Excel")
async def import_companies(
        file: UploadFile = File(...),
        role: CompanyRole | None = Query(None, description="Назначить роль всем компаниям из файла"),
):
    filename = file.filename or ""
    if not filename.lower().endswith(".xlsx"):
        raise ValidationError("Поддерживаются только файлы .xlsx")

    try:
        content = await file.read(MAX_EXCEL_FILE_SIZE + 1)
    finally:
        await file.close()
    if not content:
        raise ValidationError("Excel-файл пуст")
    if len(content) > MAX_EXCEL_FILE_SIZE:
        raise ValidationError("Размер Excel-файла не должен превышать 10 МБ")
    return await CompaniesService.import_excel(content, role=role)


@router.get("/{id}", response_model=SCompanies, summary="Получить компанию по ID")
async def get_company_by_id(id: str) -> SCompanies:
    return await CompaniesService.get_by_id(id)


@router.get(
    "",
    response_model=list[SCompaniesWithDetails],
    response_model_exclude_none=True,
    summary="Получить список компаний",
)
async def get_companies(
        data: SCompanies = Depends(),
        role: CompanyRole | None = Query(None, description="Роль компании в сделках"),
        includeDetails: bool = Query(False, description="Добавить адреса, материалы или закупки"),
        includeDeleted: bool = Query(False),
        city: str | None = Query(None, description="Город адреса компании"),
        administrativeDistrict: MoscowAdministrativeDistrict | None = Query(
            None,
            description="Административный округ Москвы",
        ),
        district: str | None = Query(None, description="Район города"),
        user: SUsersGet = Depends(get_current_user),
) -> list[SCompaniesWithDetails]:
    return await CompaniesService.list_companies(
        data,
        include_deleted=includeDeleted,
        role=role,
        include_details=includeDetails,
        user_id=user.id,
        is_privileged=user.is_privileged,
        city=city,
        administrative_district=administrativeDistrict,
        district=district,
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
