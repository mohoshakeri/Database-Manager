from dataclasses import dataclass

from core.config import DatabaseKind


@dataclass(frozen=True)
class DatabaseConnectionSchema:
    id: str
    kind: DatabaseKind
    label: str
    host: str
    port: int
    username: str
    password: str
    database: str


@dataclass(frozen=True)
class ColumnSchema:
    name: str
    type: str
    nullable: bool
    primary_key: bool


@dataclass(frozen=True)
class TableSchema:
    name: str
