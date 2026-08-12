import os
from unittest.mock import patch

from run import RUNTIME_REQUIREMENTS, build_app, ensure_runtime_dependencies, load_local_environment


def test_loads_local_environment_without_external_dependency(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# comentario\nTEST_RUN_SETTING='valor local'\nINVALID_LINE\n",
        encoding="utf-8",
    )
    os.environ.pop("TEST_RUN_SETTING", None)

    load_local_environment(env_file)

    assert os.environ.pop("TEST_RUN_SETTING") == "valor local"


def test_installs_missing_dependencies_with_current_interpreter():
    def fake_find_spec(module):
        return None if module == "flask" else object()

    with (
        patch("run.find_spec", side_effect=fake_find_spec),
        patch("run.subprocess.check_call") as install,
    ):
        ensure_runtime_dependencies()

    install.assert_called_once_with(
        [
            os.sys.executable,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            *RUNTIME_REQUIREMENTS,
        ]
    )


def test_single_entrypoint_supports_typical_create_read_delete_flow():
    app = build_app(
        {
            "TESTING": True,
            "DATABASE_URL": "sqlite+pysqlite:///:memory:",
            "USER_ID_HASH_SALT": "test-salt",
        }
    )
    client = app.test_client()
    event_id = "63811f26-0249-4f34-936a-b79e6d9cf857"

    created = client.post(
        "/api/v1/events",
        json={
            "event_id": event_id,
            "timestamp": "2026-07-13T20:04:44Z",
            "event_name": "request",
            "app_env": "production",
        },
    )
    read = client.get(f"/api/v1/events/{event_id}")
    deleted = client.delete(f"/api/v1/events/{event_id}")
    readiness = client.get("/health/ready")

    assert created.status_code == 201
    assert read.status_code == 200
    assert deleted.status_code == 204
    assert readiness.status_code == 200
