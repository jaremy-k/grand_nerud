import pytest
from pydantic import ValidationError

from app.companies.shemas import SCompaniesAdd


def test_company_accepts_multiple_roles():
    company = SCompaniesAdd(roles=["provider", "customer"])

    assert company.roles == ["provider", "customer"]


def test_company_rejects_unknown_role():
    with pytest.raises(ValidationError):
        SCompaniesAdd(roles=["contractor"])


def test_company_accepts_multiple_manual_contact_persons():
    company = SCompaniesAdd(contactPersons=[
        {
            "name": "Иван Петров",
            "position": "Директор",
            "phone": "+7 999 123-45-67",
            "email": "ivan@example.com",
        },
        {
            "name": "Анна Сидорова",
            "position": "Менеджер",
            "phone": "+7 999 765-43-21",
            "comment": "Звонить после 10:00",
        },
    ])

    payload = company.model_dump(exclude_none=True, mode="json")

    assert len(payload["contactPersons"]) == 2
    assert payload["contactPersons"][0]["email"] == "ivan@example.com"
    assert payload["contactPersons"][1]["name"] == "Анна Сидорова"


def test_company_contact_person_requires_name():
    with pytest.raises(ValidationError):
        SCompaniesAdd(contactPersons=[{"phone": "+7 999 123-45-67"}])


def test_company_accepts_import_contact_fields():
    company = SCompaniesAdd(
        phones=["+7 (495) 123-45-67", "+7 999 123-45-67"],
        emails=["info@example.com", "sales@example.com"],
        websites=["https://example.com"],
        source="Контур.Поиск клиентов",
        segments=["нерудка"],
        contactPersons=[{
            "name": "Иван Петров",
            "inn": "504216630447",
            "position": "Генеральный директор",
            "phones": ["+7 999 765-43-21"],
            "emails": ["ivan@example.com"],
            "isPrimary": True,
        }],
    )

    payload = company.model_dump(exclude_none=True, mode="json")

    assert payload["phones"] == ["+7 (495) 123-45-67", "+7 999 123-45-67"]
    assert payload["emails"] == ["info@example.com", "sales@example.com"]
    assert payload["websites"] == ["https://example.com"]
    assert payload["source"] == "Контур.Поиск клиентов"
    assert payload["segments"] == ["нерудка"]
    assert payload["contactPersons"][0]["inn"] == "504216630447"
    assert payload["contactPersons"][0]["isPrimary"] is True


def test_company_rejects_invalid_email_in_arrays():
    with pytest.raises(ValidationError):
        SCompaniesAdd(emails=["not-an-email"])

    with pytest.raises(ValidationError):
        SCompaniesAdd(contactPersons=[{
            "name": "Иван Петров",
            "emails": ["not-an-email"],
        }])
