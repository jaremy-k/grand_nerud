from app.database import database_mongo
from app.repositories.mongo import MongoRepository

adresses_repository = MongoRepository(database_mongo["adresses"])
