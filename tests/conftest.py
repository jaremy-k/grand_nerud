import os

# Минимальный набор env до импорта приложения
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("MONGO_INITDB_ROOT_USERNAME", "test")
os.environ.setdefault("MONGO_INITDB_ROOT_PASSWORD", "test")
os.environ.setdefault("MONGO_INITDB_DATABASE", "test_db")
os.environ.setdefault("API_FNS_URL", "https://example.com")
os.environ.setdefault("API_FNS_KEY", "test-key")
