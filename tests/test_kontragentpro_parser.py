from app.integrations.kontragentpro.parser import parse_company_data


def test_parse_company_data_empty():
    result = parse_company_data({})
    assert result["name"] == ""
    assert result["inn"] == 0
    assert result["contacts"] == []
    assert result["is_deleted"] is False


def test_parse_company_card():
    result = parse_company_data({
        "inn": "7707083893",
        "name": {
            "short": "ПАО СБЕРБАНК",
            "full": 'ПУБЛИЧНОЕ АКЦИОНЕРНОЕ ОБЩЕСТВО "СБЕРБАНК РОССИИ"',
        },
        "status": "active",
        "address": "117312, Г.МОСКВА, УЛ. ВАВИЛОВА, Д.19",
        "director": {"fio": "Греф Герман Оскарович", "inn": None},
        "risk": {"is_bankrupt": False},
    })

    assert result["inn"] == 7707083893
    assert result["name"] == 'ПУБЛИЧНОЕ АКЦИОНЕРНОЕ ОБЩЕСТВО "СБЕРБАНК РОССИИ"'
    assert result["abbreviatedName"] == "ПАО СБЕРБАНК"
    assert result["type"] == "Юридическое лицо"
    assert {"address": "117312, Г.МОСКВА, УЛ. ВАВИЛОВА, Д.19"} in result["contacts"]
    assert {"director": "Греф Герман Оскарович"} in result["contacts"]
    assert result["is_deleted"] is False


def test_parse_bankrupt_company():
    result = parse_company_data({
        "inn": "1234567890",
        "name": {"short": "ООО ТЕСТ", "full": "ООО ТЕСТ"},
        "status": "bankrupt",
        "risk": {"is_bankrupt": True},
    })
    assert result["is_deleted"] is True
    assert result["deleted_at"] is not None
