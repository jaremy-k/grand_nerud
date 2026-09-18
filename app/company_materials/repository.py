from app.database import database_mongo
from app.repositories.mongo import MongoRepository

company_materials_repository = MongoRepository(database_mongo["company_materials"])
