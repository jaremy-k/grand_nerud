from typing import Any, List

from bson import ObjectId
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from app.base_schemas import BaseMongoModel


class PaginatedResponse(BaseModel):
    items: List[Any]
    total: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool
    has_prev: bool

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str},
    )


class PaginationParams(BaseMongoModel):
    page: int = 1
    page_size: int = 100

    @property
    def skip(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        return self.page_size
