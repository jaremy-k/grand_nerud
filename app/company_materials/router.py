from typing import Optional

from fastapi import APIRouter, Depends, Query, status

from app.company_materials.service import CompanyMaterialsService
from app.company_materials.shemas import (
    SCompanyMaterial,
    SCompanyMaterialInput,
    SCompanyMaterialWithRelations,
)
from app.users.dependencies import get_current_user

router = APIRouter(
    prefix="/company-materials",
    tags=["Материалы компаний"],
    dependencies=[Depends(get_current_user)],
)


@router.get("", response_model=list[SCompanyMaterialWithRelations], summary="Получить материалы компаний")
async def get_company_materials(
        companyId: str | None = Query(None),
        materialId: str | None = Query(None),
        includeDeleted: bool = Query(False),
):
    return await CompanyMaterialsService.list_with_relations(
        company_id=companyId,
        material_id=materialId,
        include_deleted=includeDeleted,
    )


@router.get("/{id}", response_model=SCompanyMaterialWithRelations, summary="Получить материал компании")
async def get_company_material(id: str):
    return await CompanyMaterialsService.get_with_relations(id)


@router.post(
    "",
    response_model=SCompanyMaterial,
    summary="Добавить материал компании",
    status_code=status.HTTP_201_CREATED,
)
async def add_company_material(data: SCompanyMaterialInput):
    return await CompanyMaterialsService.create(data)


@router.patch("/{id}", response_model=SCompanyMaterial, summary="Обновить материал компании")
async def update_company_material(id: str, data: SCompanyMaterialInput):
    return await CompanyMaterialsService.update(id, data)


@router.delete("/{id}", response_model=Optional[SCompanyMaterial], summary="Удалить материал компании")
async def delete_company_material(id: str):
    return await CompanyMaterialsService.soft_delete(id)
