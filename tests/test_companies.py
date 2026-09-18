import pytest
from pydantic import ValidationError

from app.companies.shemas import SCompaniesAdd


def test_company_accepts_multiple_roles():
    company = SCompaniesAdd(roles=["provider", "customer"])

    assert company.roles == ["provider", "customer"]


def test_company_rejects_unknown_role():
    with pytest.raises(ValidationError):
        SCompaniesAdd(roles=["contractor"])
