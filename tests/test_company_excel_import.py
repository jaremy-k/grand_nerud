from io import BytesIO

import pytest
from openpyxl import Workbook

from app.companies.excel_import import CompanyExcelFormatError, parse_companies_excel


def _workbook_bytes(headers: list[str], rows: list[list]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Контрагенты"
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    buffer = BytesIO()
    workbook.save(buffer)
    workbook.close()
    return buffer.getvalue()


def test_parse_companies_excel_maps_company_and_director():
    content = _workbook_bytes(
        [
            "Наименование", "ИНН", "ФИО руководителя", "ИННФЛ руководителя",
            "Должность руководителя", "Номер телефона", "Дополнительный телефон 1",
            "Электронная почта", "Дополнительная электронная почта 1",
            "Ссылка на сайт", "Источник", "Название сегмента",
        ],
        [[
            "ООО Тест", "7701234567", "Иван Петров", "504216630447",
            "Генеральный директор", "+7 999 111-22-33", "+7 999 444-55-66",
            "info@example.com", "sales@example.com", "https://example.com",
            "Контур.Поиск клиентов", "нерудка",
        ]],
    )

    rows, errors = parse_companies_excel(content, role="provider")

    assert errors == []
    assert len(rows) == 1
    data = rows[0].data
    assert data["inn"] == "7701234567"
    assert data["phones"] == ["+7 999 111-22-33", "+7 999 444-55-66"]
    assert data["emails"] == ["info@example.com", "sales@example.com"]
    assert data["websites"] == ["https://example.com"]
    assert data["roles"] == ["provider"]
    assert data["contactPersons"] == [{
        "name": "Иван Петров",
        "isPrimary": True,
        "inn": "504216630447",
        "position": "Генеральный директор",
    }]


def test_parse_companies_excel_reports_incomplete_row():
    content = _workbook_bytes(
        ["Наименование", "ИНН"],
        [["ООО Без ИНН", None]],
    )

    rows, errors = parse_companies_excel(content)

    assert rows == []
    assert errors == [{
        "row": 2,
        "detail": "Не заполнены обязательные поля Наименование или ИНН",
    }]


def test_parse_companies_excel_requires_headers():
    content = _workbook_bytes(["Компания", "Налоговый номер"], [["ООО Тест", "123"]])

    with pytest.raises(CompanyExcelFormatError):
        parse_companies_excel(content)
