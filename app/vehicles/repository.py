from app.database import database_mongo
from app.repositories.mongo import MongoRepository

vehicles_repository = MongoRepository(database_mongo["vehicles"])
