from datetime import datetime, timezone

from app.calculator_config import repository as config_repo
from app.calculator_config.models import CalculatorConfig
from app.database import database_mongo
from app.logger import logger
from app.stages.repository import stages_repository
from bson import ObjectId

MIGRATIONS_COLLECTION = database_mongo["migrations"]
STAGES_COLLECTION = database_mongo["stages"]

DEFAULT_STAGES = [
    ("Согласование", 0),
    ("Заключение договора", 1),
    ("Ожидает оплаты", 2),
    ("Заказ выполняется", 3),
    ("Выполнен", 4),
    ("Отменен", 5),
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

    existing_stages = await stages_repository.find_many(
        filter_by={"deletedAt": None},
        limit=1000,
    )
    existing_names = {
        (stage.get("name") or "").strip().lower()
        for stage in existing_stages
    }

    created = 0
    for name, order in DEFAULT_STAGES:
        if name.lower() in existing_names:
            await STAGES_COLLECTION.update_one(
                {"name": {"$regex": f"^{name}$", "$options": "i"}, "deletedAt": None},
                {"$set": {"order": order}},
            )
            continue
        await stages_repository.create({"name": name, "order": order})
        created += 1

    logger.info("Migration: stages seeded/updated (created=%s)", created)
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


async def run_migrations() -> None:
    await migrate_calculator_config()
    await migrate_stages()
    await migrate_services_kinds()
    await migrate_calculation_rules()


async def migrate_calculation_rules() -> None:
    migration_id = "calculation_rules_v1"
    if await _is_applied(migration_id):
        return

    from app.calculation_rules.service import CalculationRulesService
    await CalculationRulesService.seed_default_rule_if_empty()
    logger.info("Migration: default calculation rules seeded")
    await _mark_applied(migration_id)
