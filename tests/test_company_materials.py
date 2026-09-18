import pytest
from bson import ObjectId
from pydantic import ValidationError

from app.company_materials.shemas import SCompanyMaterial, SCompanyMaterialInput
from app.deals.pipelines import get_deal_relation_lookups


def test_company_material_input_converts_ids():
    company_id = ObjectId()
    material_id = ObjectId()

    value = SCompanyMaterialInput(
        companyId=str(company_id),
        materialId=str(material_id),
        price=1250,
        unit="т",
    )

    assert value.companyId == company_id
    assert value.materialId == material_id


def test_company_material_rejects_negative_price():
    with pytest.raises(ValidationError):
        SCompanyMaterialInput(price=-1)


def test_company_material_response_serializes_ids():
    company_id = ObjectId()
    material_id = ObjectId()

    value = SCompanyMaterial(
        _id=ObjectId(),
        companyId=company_id,
        materialId=material_id,
        price=1250,
        unit="т",
    )

    assert value.companyId == str(company_id)
    assert value.materialId == str(material_id)


def test_deal_relations_include_provider():
    pipeline = get_deal_relation_lookups()
    provider_lookup = next(
        stage["$lookup"]
        for stage in pipeline
        if stage.get("$lookup", {}).get("as") == "provider"
    )
    add_fields = next(stage["$addFields"] for stage in pipeline if "$addFields" in stage)

    assert provider_lookup["localField"] == "providerId"
    assert provider_lookup["from"] == "companies"
    assert "provider" in add_fields
