from app.database import database_mongo
from app.repositories.mongo import MongoRepository

materials_repository = MongoRepository(database_mongo["materials"])
