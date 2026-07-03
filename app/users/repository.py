from app.database import database_mongo
from app.repositories.mongo import MongoRepository

users_repository = MongoRepository(database_mongo["users"])
