from app.database import database_mongo
from app.repositories.mongo import MongoRepository

stages_repository = MongoRepository(database_mongo["stages"])
