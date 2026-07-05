from datetime import datetime

from app.calculation_rules import repository as rules_repo
from app.calculation_rules.defaults import DEFAULT_RULE_NAME, DEFAULT_RULE_SCHEMA
from app.calculation_rules.shemas import (
    CalculationRuleCreate,
    CalculationRuleDto,
    CalculationRuleSchema,
    CalculationRuleTestInput,
    CalculationRuleTestResult,
    CalculationRuleUpdate,
    CalculationRuleValidateResult,
)
from app.calculator_config.models import CalculatorConfig
from app.calculator_config.service import CalculatorConfigService
from app.core.mongo_utils import serialize_mongo_doc
from app.exceptions import NotFoundError, ValidationError
from app.formula_engine.compiler import compile_schema, normalize_rule_document
from app.formula_engine.context import sample_context
from app.formula_engine.engine import FormulaEngine


class CalculationRulesService:
    _active_cache: dict | None = None
    _active_cache_id: str | None = None

    @classmethod
    def invalidate_cache(cls) -> None:
        cls._active_cache = None
        cls._active_cache_id = None

    @classmethod
    def _to_dto(cls, doc: dict) -> CalculationRuleDto:
        serialized = serialize_mongo_doc(doc)
        if not serialized.get("schema") and doc.get("fields"):
            from app.formula_engine.compiler import legacy_fields_to_schema
            serialized["schema"] = legacy_fields_to_schema(doc["fields"])
        return CalculationRuleDto.model_validate(serialized)

    @classmethod
    def _schema_to_dict(cls, schema: CalculationRuleSchema) -> dict:
        return schema.model_dump()

    @classmethod
    def _compile_rule_doc(cls, doc: dict):
        return normalize_rule_document(doc)

    @classmethod
    async def list_rules(cls) -> list[CalculationRuleDto]:
        docs = await rules_repo.find_all()
        return [cls._to_dto(doc) for doc in docs]

    @classmethod
    async def get_rule(cls, rule_id: str) -> CalculationRuleDto:
        doc = await rules_repo.find_by_id(rule_id)
        if not doc:
            raise NotFoundError("Набор правил не найден")
        return cls._to_dto(doc)

    @classmethod
    async def get_active_rule_document(cls) -> dict:
        if cls._active_cache is not None:
            return cls._active_cache

        doc = await rules_repo.find_active()
        if not doc:
            raise NotFoundError("Активный набор правил расчёта не найден")
        cls._active_cache = doc
        cls._active_cache_id = str(doc["_id"])
        return doc

    @classmethod
    async def get_active_rule(cls) -> CalculationRuleDto:
        return cls._to_dto(await cls.get_active_rule_document())

    @classmethod
    async def resolve_rule_document(cls, rule_id: str | None) -> dict:
        if rule_id:
            doc = await rules_repo.find_by_id(rule_id)
            if doc:
                return doc
        return await cls.get_active_rule_document()

    @classmethod
    async def create_rule(cls, data: CalculationRuleCreate) -> CalculationRuleDto:
        config = await CalculatorConfigService.get_config()
        schema_dict = cls._schema_to_dict(data.schema)
        errors = FormulaEngine.validate_schema(schema_dict, config)
        if errors:
            raise ValidationError("; ".join(errors))

        if data.isActive:
            await rules_repo.deactivate_all()
            cls.invalidate_cache()

        version = await rules_repo.get_next_version()
        now = datetime.now()
        doc = {
            "name": data.name,
            "version": version,
            "isActive": data.isActive,
            "schema": schema_dict,
            "createdAt": now,
            "updatedAt": now,
        }
        created = await rules_repo.insert(doc)
        if not created:
            raise ValidationError("Не удалось создать набор правил")
        return cls._to_dto(created)

    @classmethod
    async def update_rule(cls, rule_id: str, data: CalculationRuleUpdate) -> CalculationRuleDto:
        existing = await rules_repo.find_by_id(rule_id)
        if not existing:
            raise NotFoundError("Набор правил не найден")

        payload: dict = {"updatedAt": datetime.now()}
        if data.name is not None:
            payload["name"] = data.name
        if data.schema is not None:
            config = await CalculatorConfigService.get_config()
            schema_dict = cls._schema_to_dict(data.schema)
            errors = FormulaEngine.validate_schema(schema_dict, config)
            if errors:
                raise ValidationError("; ".join(errors))
            payload["schema"] = schema_dict

        unset_fields: list[str] = []
        if data.schema is not None:
            unset_fields.append("fields")

        if data.isActive is True:
            await rules_repo.deactivate_all()
            payload["isActive"] = True
            cls.invalidate_cache()
        elif data.isActive is False:
            payload["isActive"] = False
            if str(existing.get("_id")) == cls._active_cache_id:
                cls.invalidate_cache()

        updated = await rules_repo.update(rule_id, payload, unset=unset_fields or None)
        if not updated:
            raise ValidationError("Не удалось обновить набор правил")
        return cls._to_dto(updated)

    @classmethod
    async def activate_rule(cls, rule_id: str) -> CalculationRuleDto:
        return await cls.update_rule(rule_id, CalculationRuleUpdate(isActive=True))

    @classmethod
    async def validate_schema(cls, schema: CalculationRuleSchema) -> CalculationRuleValidateResult:
        config = await CalculatorConfigService.get_config()
        errors = FormulaEngine.validate_schema(cls._schema_to_dict(schema), config)
        return CalculationRuleValidateResult(valid=not errors, errors=errors)

    @classmethod
    async def test_schema(cls, data: CalculationRuleTestInput) -> CalculationRuleTestResult:
        config = await CalculatorConfigService.get_config()
        schema_dict = cls._schema_to_dict(data.schema)
        errors = FormulaEngine.validate_schema(schema_dict, config)
        if errors:
            return CalculationRuleTestResult(results={}, errors=errors)

        compiled = compile_schema(schema_dict)
        ctx = data.context or sample_context(config)
        deal_data = {
            key: ctx[key]
            for key in compiled.input_names
            if key in ctx
        }
        try:
            results = FormulaEngine.evaluate_rule(
                compiled=compiled,
                deal_data=deal_data,
                config=config,
                user_profit={"nonCash": {"alone": ctx.get("managerShare", 0.1)}},
            )
        except ValidationError as exc:
            return CalculationRuleTestResult(results={}, errors=[exc.detail])

        return CalculationRuleTestResult(results=results, errors=[])

    @classmethod
    async def compute_deal(
            cls,
            deal_data: dict,
            user_profit: dict | None,
            config: CalculatorConfig,
            rule_id: str | None = None,
    ) -> tuple[dict, str, int]:
        rule_doc = await cls.resolve_rule_document(rule_id)
        compiled = cls._compile_rule_doc(rule_doc)
        results = FormulaEngine.evaluate_rule(
            compiled=compiled,
            deal_data=deal_data,
            config=config,
            user_profit=user_profit,
        )
        return results, str(rule_doc["_id"]), int(rule_doc.get("version") or 1)

    @classmethod
    async def compute_deal_snapshots(
            cls,
            deal_data: dict,
            user_profit: dict | None,
            config: CalculatorConfig,
            rule_id: str | None = None,
    ) -> tuple[dict, str, int]:
        rule_doc = await cls.resolve_rule_document(rule_id)
        compiled = cls._compile_rule_doc(rule_doc)
        results = FormulaEngine.evaluate_rule(
            compiled=compiled,
            deal_data=deal_data,
            config=config,
            user_profit=user_profit,
        )
        snapshot_names = FormulaEngine.snapshot_field_names(compiled)
        snapshots = {key: value for key, value in results.items() if key in snapshot_names}
        return snapshots, str(rule_doc["_id"]), int(rule_doc.get("version") or 1)

    @classmethod
    def get_dsl_docs(cls):
        return FormulaEngine.get_dsl_docs()

    @classmethod
    async def seed_default_rule_if_empty(cls) -> None:
        active = await rules_repo.find_active()
        if active:
            return
        any_rule = await rules_repo.find_all()
        if any_rule:
            await rules_repo.update(str(any_rule[0]["_id"]), {"isActive": True, "updatedAt": datetime.now()})
            cls.invalidate_cache()
            return

        now = datetime.now()
        await rules_repo.insert({
            "name": DEFAULT_RULE_NAME,
            "version": 1,
            "isActive": True,
            "schema": DEFAULT_RULE_SCHEMA,
            "createdAt": now,
            "updatedAt": now,
        })
        cls.invalidate_cache()
