from app.database import database_mongo
from app.repositories.mongo import MongoRepository

services_repository = MongoRepository(database_mongo["services"])
