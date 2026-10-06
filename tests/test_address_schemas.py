import pytest
from pydantic import ValidationError

from app.adresses.shemas import SAdressesAdd


def test_address_accepts_moscow_geography():
    address = SAdressesAdd(
        city="Москва",
        administrativeDistrict="ЮАО",
        district="Даниловский",
    )

    assert address.city == "Москва"
    assert address.administrativeDistrict == "ЮАО"
    assert address.district == "Даниловский"


def test_address_rejects_unknown_moscow_district():
    with pytest.raises(ValidationError):
        SAdressesAdd(administrativeDistrict="Южный округ")
