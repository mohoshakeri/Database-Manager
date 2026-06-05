import pytest
from sqlalchemy import create_engine

from services import database as database_module
from services.database import DatabaseService
from schemas.database import DatabaseConnectionSchema


def test_identifier_validation_rejects_sql_injection():
    service = DatabaseService()

    service.validate_identifier("valid_name_123")

    with pytest.raises(ValueError):
        service.validate_identifier("users;DROP_TABLE_users")

    with pytest.raises(ValueError):
        service.validate_identifier("1_invalid")


def test_column_type_allowlist_rejects_raw_sql():
    service = DatabaseService()

    assert service._safe_column_type("integer") == "INTEGER"

    with pytest.raises(ValueError):
        service._safe_column_type("INTEGER); DROP TABLE users; --")


def test_parse_columns_uses_identifier_quote_and_allowlist():
    service = DatabaseService()
    engine = create_engine("sqlite+pysqlite:///:memory:")

    columns = service._parse_columns(engine, "id:integer:notnull:pk\nname:string:notnull")

    assert columns == ["id INTEGER PRIMARY KEY NOT NULL", "name VARCHAR(255) NOT NULL"]


def test_build_url_quotes_credentials():
    service = DatabaseService()
    connection = DatabaseConnectionSchema(
        id="postgres:app",
        kind="postgres",
        label="Postgres app",
        host="db.local",
        port=5432,
        username="user@example.com",
        password="p@ss word",
        database="app",
    )

    url = service._build_url(connection)

    assert url == "postgresql+psycopg2://user%40example.com:p%40ss+word@db.local:5432/app"


def test_load_connections_from_env(monkeypatch):
    monkeypatch.setattr(database_module.settings, "postgres_host", "postgres")
    monkeypatch.setattr(database_module.settings, "postgres_port", 5432)
    monkeypatch.setattr(database_module.settings, "postgres_user", "postgres")
    monkeypatch.setattr(database_module.settings, "postgres_password", "secret")
    monkeypatch.setattr(database_module.settings, "postgres_databases", "app, analytics")
    monkeypatch.setattr(database_module.settings, "mysql_databases", "")
    monkeypatch.setattr(database_module.settings, "mariadb_databases", "")

    service = DatabaseService()

    assert [connection.id for connection in service.list_connections()] == ["postgres:app", "postgres:analytics"]


def test_count_and_fetch_rows_with_pagination():
    service = DatabaseService()
    engine = create_engine("sqlite+pysqlite:///:memory:")
    service._engines["sqlite:test"] = engine

    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)")
        for index in range(1, 31):
            connection.exec_driver_sql("INSERT INTO items (id, name) VALUES (?, ?)", (index, f"item-{index}"))

    assert service.count_rows("sqlite:test", "items") == 30

    rows = service.fetch_rows("sqlite:test", "items", page=2, page_size=10)

    assert len(rows) == 10
    assert rows[0]["id"] == 11
    assert rows[-1]["id"] == 20
