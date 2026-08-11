import os
from pathlib import Path


class Config:
    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{Path.cwd() / 'instance' / 'telemetry.db'}",
    )
    USER_ID_HASH_SALT = os.getenv("USER_ID_HASH_SALT", "local-development-only")
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", str(2 * 1024 * 1024)))
    JSON_SORT_KEYS = False


class TestConfig(Config):
    TESTING = True
    DATABASE_URL = "sqlite+pysqlite:///:memory:"
    USER_ID_HASH_SALT = "test-salt"
