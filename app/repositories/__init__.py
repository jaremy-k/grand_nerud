from app.repositories.mongo import MongoRepository
from app.repositories.protocols import DealsRepositoryProtocol, EntityRepositoryProtocol

__all__ = [
    "DealsRepositoryProtocol",
    "EntityRepositoryProtocol",
    "MongoRepository",
]
