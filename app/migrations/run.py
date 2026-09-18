import re
from datetime import datetime, timezone

from bson import ObjectId

from app.calculator_config import repository as config_repo
from app.calculator_config.models import CalculatorConfig
from app.database import database_mongo
from app.logger import logger
from app.materials.repository import materials_repository
from app.stages.repository import stages_repository

MIGRATIONS_COLLECTION = database_mongo["migrations"]
STAGES_COLLECTION = database_mongo["stages"]
MATERIALS_COLLECTION = database_mongo["materials"]
DEALS_COLLECTION = database_mongo["deals"]
COMPANY_MATERIALS_COLLECTION = database_mongo["company_materials"]
COMPANIES_COLLECTION = database_mongo["companies"]

DEFAULT_STAGES = [
    ("Согласование", 0),
    ("Заключение договора", 1),
    ("Ожидает оплаты", 2),
    ("Заказ выполняется", 3),
    ("Выполнен", 4),
    ("Отменен", 5),
]

DEFAULT_MATERIALS = [
    "Песок",
    "Щебень",
    "Гравий",
    "ПГС",
    "Отсев",
    "Керамзит",
    "Чернозём",
    "Грунт",
]

SERVICE_KINDS: dict[str, str] = {
    "687a88dfb6b13b70b6a575f3": "sales",
    "698de8bf1c3ac72cbdc1ff5b": "sales_with_delivery",
    "687a88e6b6b13b70b6a575f4": "utilization",
    "687a88e9b6b13b70b6a575f5": "transport",
}

DEFAULT_SERVICES = [
    ("687a88dfb6b13b70b6a575f3", "Продажа", "sales"),
    ("698de8bf1c3ac72cbdc1ff5b", "Продажа с доставкой", "sales_with_delivery"),
    ("687a88e6b6b13b70b6a575f4", "Утилизация", "utilization"),
    ("687a88e9b6b13b70b6a575f5", "Доставка", "transport"),
]


async def _is_applied(migration_id: str) -> bool:
    doc = await MIGRATIONS_COLLECTION.find_one({"_id": migration_id})
    return doc is not None


async def _mark_applied(migration_id: str) -> None:
    await MIGRATIONS_COLLECTION.update_one(
        {"_id": migration_id},
        {"$set": {"appliedAt": datetime.now(timezone.utc)}},
        upsert=True,
    )


def _name_filter(name: str) -> dict:
    return {"name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}, "deletedAt": None}


async def _ensure_named_entities(
        collection,
        repository,
        items: list[tuple[str, dict | None]],
) -> int:
    created = 0
    for name, extra_fields in items:
        existing = await collection.find_one(_name_filter(name))
        if existing:
            if extra_fields:
                await collection.update_one(
                    {"_id": existing["_id"]},
                    {"$set": extra_fields},
                )
            continue
        document = {"name": name, **(extra_fields or {})}
        await repository.create(document)
        created += 1
    return created


async def migrate_stages_dedupe() -> None:
    migration_id = "stages_v2_dedupe"
    if await _is_applied(migration_id):
        return

    removed = 0
    cursor = STAGES_COLLECTION.aggregate([
        {"$match": {"deletedAt": None, "name": {"$exists": True, "$nin": [None, ""]}}},
        {"$group": {
            "_id": {"$toLower": {"$trim": {"input": "$name"}}},
            "docs": {"$push": {"id": "$_id", "order": "$order"}},
            "count": {"$sum": 1},
        }},
        {"$match": {"count": {"$gt": 1}}},
    ])

    async for group in cursor:
        docs = sorted(
            group["docs"],
            key=lambda doc: (
                doc.get("order") if doc.get("order") is not None else 999,
                str(doc["id"]),
            ),
        )
        keep_id = docs[0]["id"]
        for duplicate in docs[1:]:
            duplicate_id = duplicate["id"]
            await DEALS_COLLECTION.update_many(
                {"stageId": duplicate_id},
                {"$set": {"stageId": keep_id}},
            )
            await STAGES_COLLECTION.update_one(
                {"_id": duplicate_id},
                {"$set": {"deletedAt": datetime.now(timezone.utc)}},
            )
            removed += 1

    logger.info("Migration: deduped stages (removed=%s)", removed)
    await _mark_applied(migration_id)


async def migrate_calculator_config() -> None:
    migration_id = "calculator_config_v1"
    if await _is_applied(migration_id):
        return

    existing = await config_repo.find_config()
    if not existing:
        config = CalculatorConfig()
        await config_repo.upsert_config({
            "ndsPercent": config.nds_percent,
            "defaultManagerShare": config.default_manager_share,
            "cashPaymentMethod": config.cash_payment_method,
            "nonCashPaymentMethod": config.non_cash_payment_method,
            "updatedAt": datetime.now(timezone.utc),
        })
        from app.calculator_config.service import CalculatorConfigService
        CalculatorConfigService.invalidate_cache()
        logger.info("Migration: seeded calculator config")

    await _mark_applied(migration_id)


async def migrate_stages() -> None:
    migration_id = "stages_v1"
    if await _is_applied(migration_id):
        return

    created = await _ensure_named_entities(
        STAGES_COLLECTION,
        stages_repository,
        [(name, {"order": order}) for name, order in DEFAULT_STAGES],
    )

    logger.info("Migration: stages seeded/updated (created=%s)", created)
    await _mark_applied(migration_id)


async def migrate_materials() -> None:
    migration_id = "materials_v1"
    if await _is_applied(migration_id):
        return

    created = await _ensure_named_entities(
        MATERIALS_COLLECTION,
        materials_repository,
        [(name, None) for name in DEFAULT_MATERIALS],
    )

    logger.info("Migration: materials seeded (created=%s)", created)
    await _mark_applied(migration_id)


async def migrate_services_kinds() -> None:
    migration_id = "services_kinds_v1"
    if await _is_applied(migration_id):
        return

    services_collection = database_mongo["services"]
    updated = 0
    created = 0

    for service_id, name, kind in DEFAULT_SERVICES:
        oid = ObjectId(service_id)
        existing = await services_collection.find_one({"_id": oid})
        if existing:
            await services_collection.update_one(
                {"_id": oid},
                {"$set": {"kind": kind}},
            )
            updated += 1
        else:
            await services_collection.insert_one({
                "_id": oid,
                "name": name,
                "kind": kind,
            })
            created += 1

    for service_id, kind in SERVICE_KINDS.items():
        oid = ObjectId(service_id)
        await services_collection.update_one(
            {"_id": oid},
            {"$set": {"kind": kind}},
        )

    logger.info("Migration: service kinds applied (created=%s, updated=%s)", created, updated)
    await _mark_applied(migration_id)


async def migrate_calculation_rules() -> None:
    migration_id = "calculation_rules_v1"
    if await _is_applied(migration_id):
        return

    from app.calculation_rules.service import CalculationRulesService
    await CalculationRulesService.seed_default_rule_if_empty()
    logger.info("Migration: default calculation rules seeded")
    await _mark_applied(migration_id)


async def migrate_calculation_rules_schema() -> None:
    migration_id = "calculation_rules_v2"
    if await _is_applied(migration_id):
        return

    from app.formula_engine.compiler import legacy_fields_to_schema

    rules_collection = database_mongo["calculation_rules"]
    cursor = rules_collection.find({"fields": {"$exists": True}})
    migrated = 0
    async for doc in cursor:
        schema = legacy_fields_to_schema(doc["fields"])
        await rules_collection.update_one(
            {"_id": doc["_id"]},
            {"$set": {"schema": schema}, "$unset": {"fields": ""}},
        )
        migrated += 1

    from app.calculation_rules.service import CalculationRulesService
    CalculationRulesService.invalidate_cache()
    logger.info("Migration: calculation rules schema migrated (count=%s)", migrated)
    await _mark_applied(migration_id)


_DEAL_COMPUTED_FIELDS = (
    "amountPurchaseTotal",
    "amountSalesTotal",
    "ndsAmount",
    "companyProfit",
    "managerProfit",
    "totalAmount",
    "actualCompanyProfit",
    "actualAmountSalesTotal",
    "actualAmountPurchaseTotal",
    "totalDeliveredQuantity",
    "managerShare",
)


async def migrate_deals_strip_computed() -> None:
    migration_id = "deals_strip_computed_v1"
    if await _is_applied(migration_id):
        return

    result = await DEALS_COLLECTION.update_many(
        {},
        {"$unset": {field: "" for field in _DEAL_COMPUTED_FIELDS}},
    )
    logger.info("Migration: stripped computed deal fields (modified=%s)", result.modified_count)
    await _mark_applied(migration_id)


async def migrate_company_materials_indexes() -> None:
    migration_id = "company_materials_indexes_v1"
    if await _is_applied(migration_id):
        return

    await COMPANY_MATERIALS_COLLECTION.create_index([
        ("companyId", 1),
        ("materialId", 1),
        ("deletedAt", 1),
    ])
    await COMPANY_MATERIALS_COLLECTION.create_index([
        ("materialId", 1),
        ("deletedAt", 1),
    ])
    logger.info("Migration: company materials indexes created")
    await _mark_applied(migration_id)


async def migrate_company_roles() -> None:
    migration_id = "company_roles_v1"
    if await _is_applied(migration_id):
        return

    provider_ids = await DEALS_COLLECTION.distinct(
        "providerId",
        {"providerId": {"$ne": None}},
    )
    customer_ids = await DEALS_COLLECTION.distinct(
        "customerId",
        {"customerId": {"$ne": None}},
    )

    providers_updated = 0
    customers_updated = 0
    if provider_ids:
        result = await COMPANIES_COLLECTION.update_many(
            {"_id": {"$in": provider_ids}},
            {"$addToSet": {"roles": "provider"}},
        )
        providers_updated = result.modified_count
    if customer_ids:
        result = await COMPANIES_COLLECTION.update_many(
            {"_id": {"$in": customer_ids}},
            {"$addToSet": {"roles": "customer"}},
        )
        customers_updated = result.modified_count

    await COMPANIES_COLLECTION.create_index([("roles", 1), ("deletedAt", 1)])
    logger.info(
        "Migration: company roles populated (providers=%s, customers=%s)",
        providers_updated,
        customers_updated,
    )
    await _mark_applied(migration_id)


async def run_migrations() -> None:
    await migrate_stages_dedupe()
    await migrate_calculator_config()
    await migrate_stages()
    await migrate_materials()
    await migrate_services_kinds()
    await migrate_calculation_rules()
    await migrate_calculation_rules_schema()
    await migrate_deals_strip_computed()
    await migrate_company_materials_indexes()
    await migrate_company_roles()
