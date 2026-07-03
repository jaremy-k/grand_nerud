from app.integrations.fns.parser import parse_company_data


def test_parse_company_data_empty():
    result = parse_company_data({})
    assert result["name"] == ""
    assert result["inn"] == 0
