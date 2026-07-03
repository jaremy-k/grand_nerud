from datetime import datetime
from typing import Any


def parse_company_data(json_data: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "name": "",
        "abbreviatedName": "",
        "inn": 0,
        "contacts": [],
        "type": "",
        "deleted_at": None,
        "is_deleted": False,
    }

    if not json_data.get("items"):
        return result

    item = json_data["items"][0]

    if "ИП" in item:
        result["type"] = "Индивидуальный предприниматель"
        return _parse_individual_entrepreneur(item["ИП"], result)
    if "ЮЛ" in item:
        result["type"] = "Юридическое лицо"
        return _parse_legal_entity(item["ЮЛ"], result)

    return result


def _parse_individual_entrepreneur(ip_data: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    result["name"] = ip_data.get("ФИОПолн", "")
    result["abbreviatedName"] = ip_data.get("ФИОПолн", "")

    inn_str = ip_data.get("ИННФЛ", "")
    try:
        result["inn"] = int(inn_str) if inn_str else 0
    except (ValueError, TypeError):
        result["inn"] = 0

    contacts: list[dict] = []
    email = ip_data.get("E-mail") or ip_data.get("Контакты", {}).get("e-mail", [""])[0]
    if email:
        contacts.append({"email": email.lower()})

    address = ip_data.get("Адрес", {}).get("АдресПолн")
    if address:
        contacts.append({"address": address})
    result["contacts"] = contacts

    status = ip_data.get("Статус", "")
    if status and "прекращ" in status.lower() or "не действ" in status.lower():
        result["is_deleted"] = True
        result["deleted_at"] = datetime.now().isoformat()

    return result


def _parse_legal_entity(ul_data: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    result["name"] = ul_data.get("НаимПолнЮЛ", "")
    result["abbreviatedName"] = ul_data.get("НаимСокрЮЛ", "")

    inn_str = ul_data.get("ИНН", "")
    try:
        result["inn"] = int(inn_str) if inn_str else 0
    except (ValueError, TypeError):
        result["inn"] = 0

    contacts: list[dict] = []
    address = ul_data.get("Адрес", {}).get("АдресПолн")
    if address:
        contacts.append({"address": address})

    director = ul_data.get("Руководитель", {})
    if director.get("ФИОПолн"):
        contacts.append({"director": director["ФИОПолн"]})
    result["contacts"] = contacts

    status = ul_data.get("Статус", "")
    if status and any(word in status.lower() for word in ["прекращ", "ликвидир", "не действ", "исключен"]):
        result["is_deleted"] = True
        result["deleted_at"] = datetime.now().isoformat()

    return result
