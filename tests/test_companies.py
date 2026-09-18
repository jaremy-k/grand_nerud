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
