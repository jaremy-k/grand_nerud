from fastapi import APIRouter, Depends

from app.calculator_config.service import CalculatorConfigService
from app.calculator_config.shemas import CalculatorConfigDto, CalculatorConfigUpdate
from app.users.dependencies import get_current_privileged_user, get_current_user
from app.users.shemas import SUsersGet

router = APIRouter(
    prefix="/calculator-config",
    tags=["Настройки калькулятора"],
)


@router.get("", response_model=CalculatorConfigDto, summary="Получить настройки калькулятора")
async def get_calculator_config(
        _user: SUsersGet = Depends(get_current_user),
) -> CalculatorConfigDto:
    return await CalculatorConfigService.get_dto()


@router.patch("", response_model=CalculatorConfigDto, summary="Обновить настройки калькулятора (админ/руководитель)")
async def update_calculator_config(
        data: CalculatorConfigUpdate,
        _user: SUsersGet = Depends(get_current_privileged_user),
) -> CalculatorConfigDto:
    return await CalculatorConfigService.update(data)
