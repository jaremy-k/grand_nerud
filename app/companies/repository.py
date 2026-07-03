from app.database import database_mongo
from app.repositories.mongo import MongoRepository

companies_repository = MongoRepository(database_mongo["companies"])
