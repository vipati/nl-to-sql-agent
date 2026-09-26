import duckdb
from pydantic import BaseModel

# Text columns with at most this many distinct values get their values listed in the
# prompt, so the model writes status = 'completed' instead of guessing 'complete'.
MAX_SAMPLE_VALUES = 8


class Column(BaseModel):
    name: str
    data_type: str
    description: str | None = None
    primary_key: bool = False
    references: str | None = None  # "table.column" for foreign keys
    sample_values: list[str] = []


class Table(BaseModel):
    name: str
    columns: list[Column]
    description: str | None = None

    def column_names(self) -> set[str]:
        return {column.name.lower() for column in self.columns}


class DatabaseSchema(BaseModel):
    dialect: str = "duckdb"
    tables: list[Table]

    def table(self, name: str) -> Table | None:
        lowered = name.lower()
        return next((table for table in self.tables if table.name.lower() == lowered), None)

    def table_names(self) -> set[str]:
        return {table.name.lower() for table in self.tables}


def introspect_schema(connection: duckdb.DuckDBPyConnection) -> DatabaseSchema:
    """Read tables, columns, keys, comments, and low-cardinality values from a DuckDB database."""
    table_rows = connection.execute(
        "SELECT table_name, comment FROM duckdb_tables() "
        "WHERE schema_name = 'main' AND NOT internal ORDER BY table_name"
    ).fetchall()
    column_rows = connection.execute(
        "SELECT table_name, column_name, data_type, comment FROM duckdb_columns() "
        "WHERE schema_name = 'main' AND NOT internal ORDER BY table_name, column_index"
    ).fetchall()
    constraint_rows = connection.execute(
        "SELECT table_name, constraint_type, constraint_column_names, referenced_table, "
        "referenced_column_names FROM duckdb_constraints() "
        "WHERE schema_name = 'main' AND constraint_type IN ('PRIMARY KEY', 'FOREIGN KEY')"
    ).fetchall()

    primary_keys: set[tuple[str, str]] = set()
    references: dict[tuple[str, str], str] = {}
    for table, kind, columns, ref_table, ref_columns in constraint_rows:
        if kind == "PRIMARY KEY":
            primary_keys.update((table, column) for column in columns)
        else:
            for column, ref_column in zip(columns, ref_columns, strict=True):
                references[(table, column)] = f"{ref_table}.{ref_column}"

    tables = []
    for table_name, table_comment in table_rows:
        columns = [
            Column(
                name=column,
                data_type=data_type,
                description=comment or None,
                primary_key=(table, column) in primary_keys,
                references=references.get((table, column)),
                sample_values=_sample_values(connection, table, column, data_type),
            )
            for table, column, data_type, comment in column_rows
            if table == table_name
        ]
        tables.append(Table(name=table_name, columns=columns, description=table_comment or None))
    return DatabaseSchema(tables=tables)


def _sample_values(
    connection: duckdb.DuckDBPyConnection, table: str, column: str, data_type: str
) -> list[str]:
    if data_type != "VARCHAR" or column.lower() in {"name", "email"}:
        return []
    quoted_column, quoted_table = _quote(column), _quote(table)
    rows = connection.execute(
        f"SELECT DISTINCT {quoted_column} FROM {quoted_table} WHERE {quoted_column} IS NOT NULL "
        f"ORDER BY 1 LIMIT {MAX_SAMPLE_VALUES + 1}"
    ).fetchall()
    if len(rows) > MAX_SAMPLE_VALUES:
        return []
    return [str(row[0]) for row in rows]


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def format_schema_context(schema: DatabaseSchema) -> str:
    """Render the schema as commented DDL, the format LLMs read most reliably."""
    blocks: list[str] = []
    for table in schema.tables:
        lines = [f"-- {table.description}"] if table.description else []
        lines.append(f"CREATE TABLE {table.name} (")
        column_lines = []
        for column in table.columns:
            line = f"    {column.name} {column.data_type}"
            if column.primary_key:
                line += " PRIMARY KEY"
            if column.references:
                ref_table, ref_column = column.references.split(".", 1)
                line += f" REFERENCES {ref_table}({ref_column})"
            notes = []
            if column.description:
                notes.append(column.description)
            if column.sample_values:
                notes.append("values: " + ", ".join(f"'{v}'" for v in column.sample_values))
            column_lines.append((line, notes))
        for index, (line, notes) in enumerate(column_lines):
            separator = "," if index < len(column_lines) - 1 else ""
            comment = f" -- {'; '.join(notes)}" if notes else ""
            lines.append(f"{line}{separator}{comment}")
        lines.append(");")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)
