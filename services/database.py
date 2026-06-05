import re
from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import quote_plus

from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.engine import RowMapping
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.sql.compiler import IdentifierPreparer

from core.config import DatabaseKind, settings, split_csv
from schemas.database import ColumnSchema, DatabaseConnectionSchema, TableSchema

IDENTIFIER_PATTERN: re.Pattern[str] = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")
ALLOWED_COLUMN_TYPES: dict[str, str] = {
    "string": "VARCHAR(255)",
    "text": "TEXT",
    "integer": "INTEGER",
    "bigint": "BIGINT",
    "decimal": "DECIMAL(18,2)",
    "boolean": "BOOLEAN",
    "date": "DATE",
    "datetime": "TIMESTAMP",
}


class DatabaseService:
    def __init__(self) -> None:
        self._connections: dict[str, DatabaseConnectionSchema] = self._load_connections()
        self._engines: dict[str, Engine] = {}

    def list_connections(self) -> list[DatabaseConnectionSchema]:
        return list(self._connections.values())

    def get_connection(self, connection_id: str) -> DatabaseConnectionSchema:
        connection: DatabaseConnectionSchema | None = self._connections.get(connection_id)
        if not connection:
            raise ValueError("Unknown database connection")
        return connection

    def get_engine(self, connection_id: str) -> Engine:
        if connection_id not in self._engines:
            connection: DatabaseConnectionSchema = self.get_connection(connection_id)
            self._engines[connection_id] = create_engine(
                self._build_url(connection=connection),
                pool_pre_ping=True,
                pool_recycle=1800,
            )
        return self._engines[connection_id]

    def list_tables(self, connection_id: str) -> list[TableSchema]:
        engine: Engine = self.get_engine(connection_id)
        inspector = inspect(engine)
        return [TableSchema(name=name) for name in inspector.get_table_names()]

    def list_columns(self, connection_id: str, table_name: str) -> list[ColumnSchema]:
        self.validate_identifier(table_name)
        engine: Engine = self.get_engine(connection_id)
        inspector = inspect(engine)
        primary_keys: set[str] = set(inspector.get_pk_constraint(table_name).get("constrained_columns", []))
        return [
            ColumnSchema(
                name=str(column["name"]),
                type=str(column["type"]),
                nullable=bool(column["nullable"]),
                primary_key=str(column["name"]) in primary_keys,
            )
            for column in inspector.get_columns(table_name)
        ]

    def count_rows(
        self,
        connection_id: str,
        table_name: str,
        search: str = "",
        filters: Mapping[str, str] | None = None,
    ) -> int:
        self.validate_identifier(table_name)
        engine: Engine = self.get_engine(connection_id)
        quoted_table: str = self.quote_identifier(engine=engine, identifier=table_name)
        columns: list[ColumnSchema] = self.list_columns(connection_id, table_name)
        where_sql, params = self._build_where_sql(engine=engine, columns=columns, search=search, filters=filters or {})
        with engine.connect() as connection:
            total: int = int(connection.execute(text(f"SELECT COUNT(*) FROM {quoted_table}{where_sql}"), params).scalar_one())
        return total

    def fetch_rows(
        self,
        connection_id: str,
        table_name: str,
        page: int = 1,
        page_size: int = 25,
        search: str = "",
        filters: Mapping[str, str] | None = None,
        sort_by: str = "",
        sort_dir: str = "asc",
    ) -> list[dict[str, Any]]:
        self.validate_identifier(table_name)
        safe_page: int = max(page, 1)
        safe_page_size: int = min(max(page_size, 10), 100)
        offset: int = (safe_page - 1) * safe_page_size
        engine: Engine = self.get_engine(connection_id)
        quoted_table: str = self.quote_identifier(engine=engine, identifier=table_name)
        columns: list[ColumnSchema] = self.list_columns(connection_id, table_name)
        where_sql, params = self._build_where_sql(engine=engine, columns=columns, search=search, filters=filters or {})
        order_sql: str = self._order_sql(engine=engine, columns=columns, sort_by=sort_by, sort_dir=sort_dir)
        with engine.connect() as connection:
            rows: list[RowMapping] = connection.execute(
                text(f"SELECT * FROM {quoted_table}{where_sql}{order_sql} LIMIT :limit OFFSET :offset"),
                {**params, "limit": safe_page_size, "offset": offset},
            ).mappings().all()
        return [dict(row) for row in rows]

    def create_database(self, kind: DatabaseKind, database_name: str) -> None:
        self.validate_identifier(database_name)
        admin: DatabaseConnectionSchema = self._get_admin_connection(kind=kind)
        engine: Engine = create_engine(self._build_url(connection=admin, database_override=self._default_database(kind)))
        quoted_database: str = self.quote_identifier(engine=engine, identifier=database_name)
        statement: str = "CREATE DATABASE " + quoted_database
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.execute(text(statement))

    def drop_database(self, kind: DatabaseKind, database_name: str) -> None:
        self.validate_identifier(database_name)
        admin: DatabaseConnectionSchema = self._get_admin_connection(kind=kind)
        engine: Engine = create_engine(self._build_url(connection=admin, database_override=self._default_database(kind)))
        quoted_database: str = self.quote_identifier(engine=engine, identifier=database_name)
        statement: str = "DROP DATABASE " + quoted_database
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.execute(text(statement))

    def create_table(self, connection_id: str, table_name: str, columns_spec: str) -> None:
        self.validate_identifier(table_name)
        columns: list[str] = self._parse_columns(engine=self.get_engine(connection_id), columns_spec=columns_spec)
        if not columns:
            raise ValueError("At least one valid column is required")
        engine: Engine = self.get_engine(connection_id)
        quoted_table: str = self.quote_identifier(engine=engine, identifier=table_name)
        statement: str = f"CREATE TABLE {quoted_table} ({', '.join(columns)})"
        with engine.begin() as connection:
            connection.execute(text(statement))

    def drop_table(self, connection_id: str, table_name: str) -> None:
        self.validate_identifier(table_name)
        engine: Engine = self.get_engine(connection_id)
        quoted_table: str = self.quote_identifier(engine=engine, identifier=table_name)
        with engine.begin() as connection:
            connection.execute(text(f"DROP TABLE {quoted_table}"))

    def add_column(self, connection_id: str, table_name: str, column_name: str, column_type: str, nullable: bool) -> None:
        self.validate_identifier(table_name)
        self.validate_identifier(column_name)
        sql_type: str = self._safe_column_type(column_type)
        engine: Engine = self.get_engine(connection_id)
        quoted_table: str = self.quote_identifier(engine=engine, identifier=table_name)
        quoted_column: str = self.quote_identifier(engine=engine, identifier=column_name)
        null_sql: str = "" if nullable else " NOT NULL"
        with engine.begin() as connection:
            connection.execute(text(f"ALTER TABLE {quoted_table} ADD COLUMN {quoted_column} {sql_type}{null_sql}"))

    def drop_column(self, connection_id: str, table_name: str, column_name: str) -> None:
        self.validate_identifier(table_name)
        self.validate_identifier(column_name)
        engine: Engine = self.get_engine(connection_id)
        quoted_table: str = self.quote_identifier(engine=engine, identifier=table_name)
        quoted_column: str = self.quote_identifier(engine=engine, identifier=column_name)
        with engine.begin() as connection:
            connection.execute(text(f"ALTER TABLE {quoted_table} DROP COLUMN {quoted_column}"))

    def insert_row(self, connection_id: str, table_name: str, payload: Mapping[str, Any]) -> None:
        columns: list[ColumnSchema] = [column for column in self.list_columns(connection_id, table_name) if column.name in payload]
        if not columns:
            raise ValueError("No valid fields were submitted")
        engine: Engine = self.get_engine(connection_id)
        quoted_table: str = self.quote_identifier(engine=engine, identifier=table_name)
        quoted_columns: list[str] = [self.quote_identifier(engine=engine, identifier=column.name) for column in columns]
        placeholders: list[str] = [f":{column.name}" for column in columns]
        params: dict[str, Any] = {column.name: self._normalize_value(payload[column.name], column) for column in columns}
        statement: str = f"INSERT INTO {quoted_table} ({', '.join(quoted_columns)}) VALUES ({', '.join(placeholders)})"
        with engine.begin() as connection:
            connection.execute(text(statement), params)

    def update_row(self, connection_id: str, table_name: str, primary_key: str, primary_value: str, payload: Mapping[str, Any]) -> None:
        self.validate_identifier(primary_key)
        columns: list[ColumnSchema] = [
            column for column in self.list_columns(connection_id, table_name)
            if column.name in payload and column.name != primary_key
        ]
        if not columns:
            raise ValueError("No valid fields were submitted")
        engine: Engine = self.get_engine(connection_id)
        quoted_table: str = self.quote_identifier(engine=engine, identifier=table_name)
        set_sql: list[str] = [f"{self.quote_identifier(engine=engine, identifier=column.name)} = :{column.name}" for column in columns]
        params: dict[str, Any] = {column.name: self._normalize_value(payload[column.name], column) for column in columns}
        params["pk_value"] = primary_value
        quoted_pk: str = self.quote_identifier(engine=engine, identifier=primary_key)
        statement: str = f"UPDATE {quoted_table} SET {', '.join(set_sql)} WHERE {quoted_pk} = :pk_value"
        with engine.begin() as connection:
            connection.execute(text(statement), params)

    def delete_row(self, connection_id: str, table_name: str, primary_key: str, primary_value: str) -> None:
        self.validate_identifier(primary_key)
        engine: Engine = self.get_engine(connection_id)
        quoted_table: str = self.quote_identifier(engine=engine, identifier=table_name)
        quoted_pk: str = self.quote_identifier(engine=engine, identifier=primary_key)
        with engine.begin() as connection:
            connection.execute(text(f"DELETE FROM {quoted_table} WHERE {quoted_pk} = :pk_value"), {"pk_value": primary_value})

    def quote_identifier(self, engine: Engine, identifier: str) -> str:
        self.validate_identifier(identifier)
        preparer: IdentifierPreparer = engine.dialect.identifier_preparer
        return preparer.quote(identifier)

    def validate_identifier(self, identifier: str) -> None:
        if not IDENTIFIER_PATTERN.match(identifier):
            raise ValueError("Invalid identifier. Use letters, numbers, and underscores only.")

    def _load_connections(self) -> dict[str, DatabaseConnectionSchema]:
        connections: dict[str, DatabaseConnectionSchema] = {}
        for database in split_csv(settings.postgres_databases):
            self._append_connection(connections, "postgres", database)
        for database in split_csv(settings.mysql_databases):
            self._append_connection(connections, "mysql", database)
        for database in split_csv(settings.mariadb_databases):
            self._append_connection(connections, "mariadb", database)
        return connections

    def _append_connection(self, connections: dict[str, DatabaseConnectionSchema], kind: DatabaseKind, database: str) -> None:
        self.validate_identifier(database)
        host, port, username, password = self._settings_for_kind(kind)
        if not host or not username:
            return
        connection_id: str = f"{kind}:{database}"
        connections[connection_id] = DatabaseConnectionSchema(
            id=connection_id,
            kind=kind,
            label=f"{kind.upper()} / {database}",
            host=host,
            port=port,
            username=username,
            password=password,
            database=database,
        )

    def _get_admin_connection(self, kind: DatabaseKind) -> DatabaseConnectionSchema:
        host, port, username, password = self._settings_for_kind(kind)
        if not host or not username:
            raise ValueError(f"{kind} connection is not configured")
        return DatabaseConnectionSchema(
            id=f"{kind}:admin",
            kind=kind,
            label=f"{kind.upper()} admin",
            host=host,
            port=port,
            username=username,
            password=password,
            database=self._default_database(kind),
        )

    def _settings_for_kind(self, kind: DatabaseKind) -> tuple[str, int, str, str]:
        if kind == "postgres":
            return settings.postgres_host, settings.postgres_port, settings.postgres_user, settings.postgres_password
        if kind == "mysql":
            return settings.mysql_host, settings.mysql_port, settings.mysql_user, settings.mysql_password
        return settings.mariadb_host, settings.mariadb_port, settings.mariadb_user, settings.mariadb_password

    def _build_url(self, connection: DatabaseConnectionSchema, database_override: str | None = None) -> str:
        database: str = database_override or connection.database
        username: str = quote_plus(connection.username)
        password: str = quote_plus(connection.password)
        host: str = connection.host
        port: int = connection.port
        if connection.kind == "postgres":
            return f"postgresql+psycopg2://{username}:{password}@{host}:{port}/{database}"
        return f"mysql+pymysql://{username}:{password}@{host}:{port}/{database}?charset=utf8mb4"

    def _default_database(self, kind: DatabaseKind) -> str:
        if kind == "postgres":
            return "postgres"
        return "mysql"

    def _parse_columns(self, engine: Engine, columns_spec: str) -> list[str]:
        columns: list[str] = []
        for line in columns_spec.splitlines():
            parts: list[str] = [part.strip() for part in line.split(":")]
            if len(parts) < 2 or not parts[0]:
                continue
            column_name: str = parts[0]
            column_type: str = parts[1]
            nullable: bool = len(parts) < 3 or parts[2].lower() not in {"notnull", "required", "no"}
            primary_key: bool = len(parts) >= 4 and parts[3].lower() in {"pk", "primary"}
            self.validate_identifier(column_name)
            sql_type: str = self._safe_column_type(column_type)
            quoted_column: str = self.quote_identifier(engine=engine, identifier=column_name)
            flags: list[str] = []
            if primary_key:
                flags.append("PRIMARY KEY")
            if not nullable:
                flags.append("NOT NULL")
            columns.append(" ".join([quoted_column, sql_type, *flags]))
        return columns

    def _safe_column_type(self, column_type: str) -> str:
        sql_type: str | None = ALLOWED_COLUMN_TYPES.get(column_type.strip().lower())
        if not sql_type:
            raise ValueError("Unsupported column type")
        return sql_type

    def _build_where_sql(
        self,
        engine: Engine,
        columns: list[ColumnSchema],
        search: str = "",
        filters: Mapping[str, str] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        clauses: list[str] = []
        params: dict[str, Any] = {}
        column_by_name: dict[str, ColumnSchema] = {column.name: column for column in columns}

        for index, column in enumerate(columns):
            raw_value: str = str((filters or {}).get(column.name, "")).strip()
            if not raw_value:
                continue
            quoted_column: str = self.quote_identifier(engine=engine, identifier=column.name)
            param_name: str = f"filter_{index}"
            if self._is_text_column(column):
                clauses.append(f"LOWER({self._text_cast_sql(engine, quoted_column)}) LIKE :{param_name}")
                params[param_name] = f"%{raw_value.lower()}%"
            else:
                try:
                    params[param_name] = self._normalize_value(raw_value, column)
                except (ValueError, InvalidOperation):
                    clauses.append("1 = 0")
                    continue
                clauses.append(f"{quoted_column} = :{param_name}")

        search_value: str = search.strip()
        if search_value:
            search_clauses: list[str] = []
            for index, column in enumerate(columns):
                quoted_column = self.quote_identifier(engine=engine, identifier=column.name)
                param_name = f"search_{index}"
                search_clauses.append(f"LOWER({self._text_cast_sql(engine, quoted_column)}) LIKE :{param_name}")
                params[param_name] = f"%{search_value.lower()}%"
            if search_clauses:
                clauses.append("(" + " OR ".join(search_clauses) + ")")

        if not clauses:
            return "", params
        return " WHERE " + " AND ".join(clauses), params

    def _order_sql(self, engine: Engine, columns: list[ColumnSchema], sort_by: str = "", sort_dir: str = "asc") -> str:
        column_by_name: dict[str, ColumnSchema] = {column.name: column for column in columns}
        if sort_by and sort_by in column_by_name:
            direction: str = "DESC" if sort_dir.lower() == "desc" else "ASC"
            quoted_column: str = self.quote_identifier(engine=engine, identifier=sort_by)
            return f" ORDER BY {quoted_column} {direction}"

        primary_columns: list[ColumnSchema] = [column for column in columns if column.primary_key]
        order_columns: list[ColumnSchema] = primary_columns or columns
        if not order_columns:
            return ""
        quoted_columns: list[str] = [self.quote_identifier(engine=engine, identifier=column.name) for column in order_columns]
        return " ORDER BY " + ", ".join(quoted_columns)

    def _is_text_column(self, column: ColumnSchema) -> bool:
        column_type: str = column.type.lower()
        return any(marker in column_type for marker in ("char", "text", "uuid", "json", "enum"))

    def _text_cast_sql(self, engine: Engine, quoted_column: str) -> str:
        if engine.dialect.name in {"mysql", "mariadb"}:
            return f"CAST({quoted_column} AS CHAR)"
        return f"CAST({quoted_column} AS TEXT)"

    def _normalize_value(self, value: Any, column: ColumnSchema | None = None) -> Any:
        if isinstance(value, str):
            value = value.strip()
            if value == "":
                return None
        if column is None or value is None:
            return value

        column_type: str = column.type.lower()
        if "bool" in column_type or column_type in {"tinyint(1)", "bit"}:
            if isinstance(value, bool):
                return value
            return str(value).lower() in {"1", "true", "on", "yes"}
        if any(marker in column_type for marker in ("bigint", "integer", "int")) and "interval" not in column_type:
            return int(value)
        if any(marker in column_type for marker in ("decimal", "numeric", "float", "double", "real")):
            return Decimal(str(value))
        if "timestamp" in column_type or "datetime" in column_type:
            if isinstance(value, datetime):
                return value
            normalized = str(value).replace("T", " ")
            return datetime.fromisoformat(normalized)
        if column_type == "date" or column_type.startswith("date"):
            if isinstance(value, date):
                return value
            return date.fromisoformat(str(value))
        return value


database_service: DatabaseService = DatabaseService()
