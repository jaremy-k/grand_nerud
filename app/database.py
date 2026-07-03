from motor.motor_asyncio import AsyncIOMotorClient

from app.config import settings

client_mongo = AsyncIOMotorClient(settings.MONGO_URL)
database_mongo = client_mongo[settings.MONGO_INITDB_DATABASE]
