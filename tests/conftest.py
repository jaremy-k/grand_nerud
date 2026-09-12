import os

# Минимальный набор env до импорта приложения
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("MONGO_INITDB_ROOT_USERNAME", "test")
os.environ.setdefault("MONGO_INITDB_ROOT_PASSWORD", "test")
os.environ.setdefault("MONGO_INITDB_DATABASE", "test_db")
os.environ.setdefault("API_KONTRAGENTPRO_URL", "https://kontragentpro.ru/api/v2")
os.environ.setdefault("API_KONTRAGENTPRO_KEY", "test-key")
