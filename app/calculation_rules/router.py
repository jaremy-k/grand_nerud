from fastapi import APIRouter, Depends

from app.calculation_rules.service import CalculationRulesService
from app.calculation_rules.shemas import (
    CalculationRuleCreate,
    CalculationRuleDto,
    CalculationRuleDslDocs,
    CalculationRuleTestInput,
    CalculationRuleTestResult,
    CalculationRuleUpdate,
    CalculationRuleValidateResult,
    FormulaFieldSchema,
)
from app.formula_engine.engine import FormulaEngine
from app.users.dependencies import get_current_admin_user, get_current_user
from app.users.shemas import SUsersGet

router = APIRouter(
    prefix="/calculation-rules",
    tags=["Правила расчёта"],
)


@router.get("/dsl-docs", response_model=CalculationRuleDslDocs, summary="Справка по DSL")
async def get_dsl_docs(_user: SUsersGet = Depends(get_current_user)) -> CalculationRuleDslDocs:
    docs = FormulaEngine.get_dsl_docs()
    return CalculationRuleDslDocs(**docs)


@router.get("/active", response_model=CalculationRuleDto, summary="Активный набор правил")
async def get_active_rule(_user: SUsersGet = Depends(get_current_user)) -> CalculationRuleDto:
    return await CalculationRulesService.get_active_rule()


@router.post("/validate", response_model=CalculationRuleValidateResult, summary="Проверить формулы (админ)")
async def validate_rules(
        fields: list[FormulaFieldSchema],
        _user: SUsersGet = Depends(get_current_admin_user),
) -> CalculationRuleValidateResult:
    return await CalculationRulesService.validate_fields(fields)


@router.post("/test", response_model=CalculationRuleTestResult, summary="Тестовый прогон формул (админ)")
async def test_rules(
        data: CalculationRuleTestInput,
        _user: SUsersGet = Depends(get_current_admin_user),
) -> CalculationRuleTestResult:
    return await CalculationRulesService.test_fields(data)


@router.get("", response_model=list[CalculationRuleDto], summary="Все наборы правил (админ)")
async def list_rules(_user: SUsersGet = Depends(get_current_admin_user)) -> list[CalculationRuleDto]:
    return await CalculationRulesService.list_rules()


@router.post("", response_model=CalculationRuleDto, summary="Создать набор правил (админ)")
async def create_rule(
        data: CalculationRuleCreate,
        _user: SUsersGet = Depends(get_current_admin_user),
) -> CalculationRuleDto:
    return await CalculationRulesService.create_rule(data)


@router.get("/{rule_id}", response_model=CalculationRuleDto, summary="Набор правил по ID")
async def get_rule(rule_id: str, _user: SUsersGet = Depends(get_current_user)) -> CalculationRuleDto:
    return await CalculationRulesService.get_rule(rule_id)


@router.patch("/{rule_id}", response_model=CalculationRuleDto, summary="Обновить набор правил (админ)")
async def update_rule(
        rule_id: str,
        data: CalculationRuleUpdate,
        _user: SUsersGet = Depends(get_current_admin_user),
) -> CalculationRuleDto:
    return await CalculationRulesService.update_rule(rule_id, data)


@router.post("/{rule_id}/activate", response_model=CalculationRuleDto, summary="Активировать набор (админ)")
async def activate_rule(
        rule_id: str,
        _user: SUsersGet = Depends(get_current_admin_user),
) -> CalculationRuleDto:
    return await CalculationRulesService.activate_rule(rule_id)
