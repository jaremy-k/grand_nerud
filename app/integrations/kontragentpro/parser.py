from datetime import datetime
from typing import Any


def parse_company_data(json_data: dict[str, Any] | None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "name": "",
        "abbreviatedName": "",
        "inn": 0,
        "contacts": [],
        "type": "Юридическое лицо",
        "deleted_at": None,
        "is_deleted": False,
    }

    if not json_data:
        return result

    name_block = json_data.get("name")
    full_name, short_name = _extract_names(name_block)
    result["name"] = full_name or short_name
    result["abbreviatedName"] = short_name or full_name

    inn_str = json_data.get("inn") or ""
    try:
        result["inn"] = int(inn_str) if inn_str else 0
    except (ValueError, TypeError):
        result["inn"] = 0

    contacts: list[dict] = []
    address = json_data.get("address")
    if address:
        contacts.append({"address": address})

    director = json_data.get("director") or {}
    if isinstance(director, dict) and director.get("fio"):
        contacts.append({"director": director["fio"]})
    elif isinstance(director, str) and director.strip():
        contacts.append({"director": director.strip()})
    result["contacts"] = contacts

    if _is_inactive(json_data.get("status"), json_data.get("risk")):
        result["is_deleted"] = True
        result["deleted_at"] = datetime.now().isoformat()

    return result


def _extract_names(name_block: Any) -> tuple[str, str]:
    if isinstance(name_block, dict):
        full_name = str(name_block.get("full") or "").strip()
        short_name = str(name_block.get("short") or "").strip()
        return full_name, short_name
    if isinstance(name_block, str):
        value = name_block.strip()
        return value, value
    return "", ""


def _is_inactive(status: Any, risk: Any) -> bool:
    if isinstance(risk, dict) and risk.get("is_bankrupt"):
        return True
    if not status:
        return False
    normalized = str(status).strip().lower()
    return normalized not in {"active", "действующее", "действующий"}
