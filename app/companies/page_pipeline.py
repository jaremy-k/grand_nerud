import re

from app.companies.pipelines import _addresses_lookup, _company_materials_lookup
from app.companies.shemas import SCompanyPageQuery
from app.core.object_id import parse_object_id
from app.exceptions import ValidationError


UNIT_ALIASES = {"т": ["т", "тонна", "тонн", "тонны"], "м³": ["м³", "м3", "куб.м", "куб. м"], "шт": ["шт", "шт.", "штука", "штук"]}


def normalized_unit(value: str) -> str:
    value = value.strip().lower()
    return next((key for key, aliases in UNIT_ALIASES.items() if value in aliases), value)


def build_company_page_pipeline(data: SCompanyPageQuery) -> list[dict]:
    if (data.priceUnit or data.maxPrice is not None or data.priceSort != "default") and not data.materialId:
        raise ValidationError("Для фильтрации цен выберите материал")
    if (data.maxPrice is not None or data.priceSort != "default") and not data.priceUnit:
        raise ValidationError("Для сравнения цен выберите единицу")
    match = {"deletedAt": None}
    if data.role:
        match["roles"] = data.role
    search = (data.search or "").strip()
    if search:
        pattern = {"$regex": re.escape(search), "$options": "i"}
        fields = ("name", "abbreviatedName", "inn", "kpp", "phones", "emails", "websites", "source", "segments",
                  "contactPersons.name", "contactPersons.inn", "contactPersons.position", "contactPersons.phone", "contactPersons.email", "contactPersons.phones", "contactPersons.emails")
        match["$or"] = [{field: pattern} for field in fields]
        for field in ("inn", "kpp"):
            match["$or"].append({"$expr": {"$regexMatch": {"input": {"$convert": {"input": f"${field}", "to": "string", "onError": "", "onNull": ""}}, "regex": re.escape(search), "options": "i"}}})
    pipeline = [{"$match": match}]
    geo = bool(data.city or data.administrativeDistrict or data.district)
    if geo:
        pipeline.extend([_addresses_lookup(data.city, data.administrativeDistrict, data.district), {"$match": {"addresses.0": {"$exists": True}}}])
    if data.materialId:
        material = parse_object_id(data.materialId, "materialId")
        pipeline.append(_company_materials_lookup())
        conditions = [{"$eq": ["$$item.materialId", material]}, {"$isNumber": "$$item.price"}]
        if data.priceUnit:
            unit = normalized_unit(data.priceUnit)
            conditions.append({"$in": [{"$toLower": {"$trim": {"input": "$$item.unit"}}}, UNIT_ALIASES.get(unit, [unit])]})
        pipeline.extend([
            {"$set": {"materialsWithPrices": {"$filter": {"input": "$materialsWithPrices", "as": "item", "cond": {"$and": conditions}}}}},
            {"$match": {"materialsWithPrices.0": {"$exists": True}}},
            {"$set": {"_comparablePrice": {"$min": "$materialsWithPrices.price"}}},
        ])
        if data.maxPrice is not None:
            pipeline.append({"$match": {"_comparablePrice": {"$lte": data.maxPrice}}})
    sort = {"_id": -1} if data.sortBy == "recent" else {"name": 1, "_id": 1}
    if data.priceSort != "default":
        sort = {"_comparablePrice": 1 if data.priceSort == "asc" else -1, "_id": 1}
    items = [{"$sort": sort}, {"$skip": (data.page - 1) * data.pageSize}, {"$limit": data.pageSize}]
    if data.includeDetails:
        if not geo:
            items.append(_addresses_lookup())
        if not data.materialId:
            items.append(_company_materials_lookup())
    else:
        items.append({"$project": {"addresses": 0, "materialsWithPrices": 0}})
    items.append({"$project": {"_comparablePrice": 0}})
    pipeline.append({"$facet": {"items": items, "total": [{"$count": "value"}]}})
    return pipeline
