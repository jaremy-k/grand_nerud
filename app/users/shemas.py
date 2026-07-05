from datetime import datetime

from bson import ObjectId
from pydantic import BaseModel, EmailStr, Field, field_validator, computed_field


class SUsersAuth(BaseModel):
    email: EmailStr
    password: str

    class Config:
        json_encoders = {ObjectId: str}


class SUserAuth(BaseModel):
    email: EmailStr
    hashed_password: str

    class Config:
        json_encoders = {ObjectId: str}


class SUsersGet(BaseModel):
    id: str | None = Field(None, alias="_id")
    name: str | None = None
    lastName: str | None = None
    fatherName: str | None = None
    email: str | None = None
    profit: dict | None = None
    admin: bool | None = False
    manager: bool | None = False
    hashed_password: str | None = None
    deletedAt: datetime | None = None

    @computed_field
    @property
    def isDeleted(self) -> bool:
        return self.deletedAt is not None

    @computed_field
    @property
    def is_privileged(self) -> bool:
        return bool(self.admin or self.manager)

    @field_validator("id", mode="before")
    def convert_objectid(cls, v):
        if isinstance(v, ObjectId):
            return str(v)
        return v

    class Config:
        from_attributes = True
        populate_by_name = True


class SUsersUpdate(BaseModel):
    email: EmailStr | None = None
    password: str | None = Field(None, min_length=6)
    name: str | None = None
    lastName: str | None = None
    fatherName: str | None = None
    profit: dict | None = None
    admin: bool | None = None
    manager: bool | None = None


class SUsersCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6)
    name: str | None = None
    lastName: str | None = None
    fatherName: str | None = None
    profit: dict | None = None
    admin: bool | None = False
    manager: bool | None = False


class SUsersGetResponse(BaseModel):
    id: str | None = Field(None, alias="_id")
    name: str | None = None
    lastName: str | None = None
    fatherName: str | None = None
    email: str | None = None
    profit: dict | None = None
    admin: bool | None = False
    manager: bool | None = False
    deletedAt: datetime | None = None

    @computed_field
    @property
    def isDeleted(self) -> bool:
        return self.deletedAt is not None

    @field_validator("id", mode="before")
    def convert_objectid(cls, v):
        if isinstance(v, ObjectId):
            return str(v)
        return v

    class Config:
        from_attributes = True
        populate_by_name = True
