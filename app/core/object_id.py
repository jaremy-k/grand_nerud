from bson import ObjectId
from bson.errors import InvalidId

from app.exceptions import ValidationError


def parse_object_id(value: str, field: str = "id") -> ObjectId:
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        raise ValidationError(f"Невалидный {field}")
