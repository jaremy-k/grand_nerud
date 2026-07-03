import pytest

from app.core.object_id import parse_object_id
from app.exceptions import ValidationError


def test_parse_object_id_valid():
    oid = parse_object_id("507f1f77bcf86cd799439011")
    assert str(oid) == "507f1f77bcf86cd799439011"


def test_parse_object_id_invalid():
    with pytest.raises(ValidationError) as exc:
        parse_object_id("not-an-id")
    assert exc.value.status_code == 422
