import pytest

from telemetry import create_app


@pytest.fixture()
def app():
    return create_app(
        {
            "TESTING": True,
            "DATABASE_URL": "sqlite+pysqlite:///:memory:",
            "USER_ID_HASH_SALT": "test-salt",
        }
    )


@pytest.fixture()
def client(app):
    return app.test_client()
