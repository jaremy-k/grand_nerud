from app.database import database_mongo
from app.repositories.mongo import MongoRepository

lead_stages_repository = MongoRepository(database_mongo["lead_stages"])
