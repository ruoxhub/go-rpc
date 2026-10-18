from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
BACKEND = Path(__file__).resolve().parents[1]
COMPOSE_FILE = ROOT / "deploy" / "compose.yaml" if (ROOT / "deploy" / "compose.yaml").is_file() else ROOT / "compose.yaml"


def test_compose_exposes_only_frontend_and_loopback_backend():
    compose = COMPOSE_FILE.read_text(encoding="utf-8")
    assert '"3000:3000"' in compose
    assert '"127.0.0.1:8081:8081"' in compose
    assert "5432:5432" not in compose
    assert "6379:6379" not in compose
    assert "postgres_data:" in compose
    assert "redis_data:" in compose
    assert "backend_logs:" in compose


def test_compose_requires_database_and_redis_credentials():
    compose = COMPOSE_FILE.read_text(encoding="utf-8")
    for name in ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB", "REDIS_PASSWORD"):
        assert f"${{{name}:?" in compose


def test_compose_forwards_credential_fernet_keys():
    compose = COMPOSE_FILE.read_text(encoding="utf-8")

    assert "CRAWLER_CREDENTIAL_FERNET_KEYS" in compose
    assert "CRAWLER_CREDENTIAL_FERNET_KEYS:-" in compose


def test_docker_env_example_keeps_secrets_empty():
    values = dict(
        line.split("=", 1)
        for line in (ROOT / ".env.docker.example").read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    )
    for name in (
        "POSTGRES_PASSWORD",
        "REDIS_PASSWORD",
        "SEKIRO_TOKEN",
        "CRAWLER_MINIO_PASSWORD",
        "OPENAI_API_KEY",
        "CRAWLER_CREDENTIAL_FERNET_KEYS",
    ):
        assert values[name] == ""


def test_local_env_example_keeps_credential_key_empty():
    values = dict(
        line.split("=", 1)
        for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    )

    assert values["CRAWLER_CREDENTIAL_FERNET_KEYS"] == ""


def test_backend_dockerignore_excludes_python_bytecode_after_app_allowlist():
    rules = (BACKEND / ".dockerignore").read_text(encoding="utf-8").splitlines()
    allowlist_index = rules.index("!app/**")

    assert rules.index("**/__pycache__/") > allowlist_index
    assert rules.index("**/*.py[cod]") > allowlist_index


def test_backend_image_includes_llm_provider_migration_script():
    backend = BACKEND
    rules = (backend / ".dockerignore").read_text(encoding="utf-8").splitlines()
    dockerfile = (backend / "Dockerfile").read_text(encoding="utf-8")

    assert "!scripts/" in rules
    for migration in (
        "scripts/migrate_llm_provider_formats.sql",
        "scripts/migrate_llm_provider_credentials.py",
    ):
        assert (backend / migration).is_file()
        assert f"!{migration}" in rules
        assert (
            "COPY --chown=crawlstore:crawlstore "
            f"{migration} /app/{migration}"
        ) in dockerfile
