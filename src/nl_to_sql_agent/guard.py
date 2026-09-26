"""SQL guard: decides whether generated SQL may run, before it reaches the database.

The guard parses SQL into an AST with sqlglot and checks it against an allowlist:

1. Exactly one statement, and it must be a read-only query (SELECT / WITH / UNION ...).
2. No write, DDL, or session nodes anywhere in the tree (INSERT, ATTACH, COPY, SET, PRAGMA ...).
3. Tables must be plain tables from the application schema; table functions such as
   read_csv() or query() and other schemas such as information_schema are rejected.
4. No functions that read files, the environment, or engine settings.
5. Every table and column must exist in the schema, with "did you mean" hints that
   feed the repair loop.

The query that runs is re-rendered from the checked AST with a row limit pushed down,
so the database executes exactly what was validated.
"""

import difflib
import logging
from dataclasses import dataclass, field
from typing import Literal

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError
from sqlglot.optimizer.scope import Scope, traverse_scope

from nl_to_sql_agent.schema import DatabaseSchema

# sqlglot logs a warning whenever it falls back to parsing a statement as a raw Command.
# The guard rejects those statements anyway, so the warning is noise.
logging.getLogger("sqlglot").setLevel(logging.ERROR)

MAX_SQL_LENGTH = 10_000

_FORBIDDEN_NODE_NAMES = (
    "Insert", "Update", "Delete", "Merge", "Create", "Drop", "Alter", "TruncateTable",
    "Command", "Copy", "Attach", "Detach", "Pragma", "Set", "Use", "Install", "Into",
    "Transaction", "Commit", "Rollback", "LoadData", "Grant", "Revoke", "Kill", "Analyze",
    "Export", "Describe", "Show", "Summarize", "Cache", "Uncache", "Refresh",
)  # fmt: skip
FORBIDDEN_NODES: tuple[type[exp.Expression], ...] = tuple(
    node
    for node in (getattr(exp, name, None) for name in _FORBIDDEN_NODE_NAMES)
    if isinstance(node, type)
)

DENIED_FUNCTIONS = {
    "getenv", "current_setting", "query", "query_table", "glob", "sniff_csv", "load",
    "install", "checkpoint", "force_checkpoint", "sql_auto_complete", "which_secret",
}  # fmt: skip
DENIED_FUNCTION_PREFIXES = (
    "read_", "duckdb_", "pragma_", "sqlite_", "postgres_", "mysql_", "iceberg_", "delta_",
    "parquet_", "http", "s3_",
)  # fmt: skip

ErrorKind = Literal["syntax", "unsafe", "schema"]


@dataclass
class GuardResult:
    ok: bool
    sql: str
    error_kind: ErrorKind | None = None
    error: str | None = None
    tables: list[str] = field(default_factory=list)


@dataclass
class SchemaIssue:
    kind: Literal["table", "column"]
    node: exp.Expression
    name: str
    candidates: list[str]
    message: str


class UnsafeSQLError(ValueError):
    pass


def check_sql(
    sql: str,
    schema: DatabaseSchema,
    row_limit: int | None = None,
) -> GuardResult:
    """Validate SQL; on success, `result.sql` is the query to execute."""
    try:
        expression = parse_single_query(sql, schema.dialect)
    except UnsafeSQLError as error:
        return GuardResult(ok=False, sql=sql, error_kind="unsafe", error=str(error))
    except SqlglotError as error:
        return GuardResult(ok=False, sql=sql, error_kind="syntax", error=_first_line(error))

    try:
        _check_safety(expression)
    except UnsafeSQLError as error:
        return GuardResult(ok=False, sql=sql, error_kind="unsafe", error=str(error))

    issues = find_schema_issues(expression, schema)
    if issues:
        message = " ".join(dict.fromkeys(issue.message for issue in issues))
        return GuardResult(ok=False, sql=sql, error_kind="schema", error=message)

    if row_limit is not None:
        expression = apply_row_limit(expression, row_limit)
    tables = sorted({table.name for table in expression.find_all(exp.Table)} & _names(schema))
    return GuardResult(ok=True, sql=expression.sql(dialect=schema.dialect), tables=tables)


def parse_single_query(sql: str, dialect: str = "duckdb") -> exp.Query:
    text = sql.strip()
    if not text:
        raise UnsafeSQLError("Empty SQL.")
    if len(text) > MAX_SQL_LENGTH:
        raise UnsafeSQLError(f"SQL is longer than {MAX_SQL_LENGTH} characters.")
    statements = [statement for statement in sqlglot.parse(text, read=dialect) if statement]
    if len(statements) != 1:
        raise UnsafeSQLError(f"Exactly one statement is allowed; found {len(statements)}.")
    statement = statements[0]
    if not isinstance(statement, exp.Query):
        raise UnsafeSQLError(
            f"Only read-only SELECT queries are allowed; found {statement.key.upper()}."
        )
    return statement


def _check_safety(expression: exp.Expression) -> None:
    for node in expression.walk():
        if isinstance(node, FORBIDDEN_NODES):
            raise UnsafeSQLError(f"{node.key.upper()} is not allowed in a read-only query.")

    for function in expression.find_all(exp.Func):
        name = (
            function.name if isinstance(function, exp.Anonymous) else function.sql_name()
        ).lower()
        if name in DENIED_FUNCTIONS or name.startswith(DENIED_FUNCTION_PREFIXES):
            raise UnsafeSQLError(f"Function {name}() is not allowed.")

    for table in expression.find_all(exp.Table):
        if not isinstance(table.this, exp.Identifier):
            raise UnsafeSQLError(
                f"Table functions are not allowed: {table.this.sql(dialect='duckdb')}."
            )
        if table.args.get("catalog") or (table.db and table.db.lower() != "main"):
            raise UnsafeSQLError(
                f"Only tables in the application schema can be queried: {table.sql()}."
            )


def find_schema_issues(expression: exp.Expression, schema: DatabaseSchema) -> list[SchemaIssue]:
    """Unknown tables and columns, each with ranked suggestions from the schema."""
    issues: list[SchemaIssue] = []
    cte_names = {cte.alias_or_name.lower() for cte in expression.find_all(exp.CTE)}
    table_names = sorted(table.name for table in schema.tables)

    for table in expression.find_all(exp.Table):
        name = table.name.lower()
        if name in cte_names or schema.table(name):
            continue
        candidates = suggest(table.name, table_names, plural=True)
        issues.append(
            SchemaIssue("table", table, table.name, candidates,
                        f"Table '{table.name}' does not exist.{_hint(candidates)}")
        )  # fmt: skip
    if issues:
        # Column checks are unreliable until every table resolves.
        return issues

    try:
        scopes = traverse_scope(expression)
    except (SqlglotError, KeyError, ValueError):
        return issues  # unusual syntax: leave the final say to the database
    for scope in scopes:
        for column in scope.columns:
            if isinstance(column.this, exp.Star) or column.find_ancestor(exp.Lambda):
                continue
            issue = _check_column(column, scope, schema)
            if issue:
                issues.append(issue)
    return issues


def _check_column(column: exp.Column, scope: Scope, schema: DatabaseSchema) -> SchemaIssue | None:
    name = column.name
    qualifier = column.table
    if qualifier:
        source = _find_source(scope, qualifier)
        if source is None:
            candidates = suggest(qualifier, sorted(_visible_sources(scope)))
            return SchemaIssue("column", column, name, [],
                               f"'{qualifier}.{name}' refers to unknown table or alias "
                               f"'{qualifier}'.{_hint(candidates)}")  # fmt: skip
        known = _source_columns(source, schema)
        if known is None or name.lower() in {c.lower() for c in known}:
            return None
        candidates = suggest(name, sorted(known))
        table_label = source.name if isinstance(source, exp.Table) else qualifier
        return SchemaIssue("column", column, name, candidates,
                           f"Column '{name}' does not exist in '{table_label}'."
                           f"{_hint(candidates)}")  # fmt: skip

    # Which sources expose each column, so a name shared by two joined tables is ambiguous.
    owners: dict[str, list[str]] = {}
    current: Scope | None = scope
    while current is not None:
        for alias, source in current.sources.items():
            source_columns = _source_columns(source, schema)
            if source_columns is None:
                return None  # a source with unknown columns (e.g. SELECT *): can't judge
            for source_column in source_columns:
                owners.setdefault(source_column, []).append(alias)
        for output_alias in _output_aliases(current.expression):
            owners.setdefault(output_alias, [])
        current = current.parent
    if name.lower() in {c.lower() for c in owners}:
        return None
    candidates = [
        f"{owner}.{candidate}" if len(owners[candidate]) > 1 else candidate
        for candidate in suggest(name, sorted(owners))
        for owner in (owners[candidate] if len(owners[candidate]) > 1 else [""])
    ]
    return SchemaIssue("column", column, name, candidates,
                       f"Column '{name}' does not exist in the tables used by this query."
                       f"{_hint(candidates) or _elsewhere_hint(name, schema)}")  # fmt: skip


def _elsewhere_hint(name: str, schema: DatabaseSchema) -> str:
    """Point at schema tables the query does not use, e.g. when FROM or a JOIN is missing."""
    tables = [table.name for table in schema.tables if name.lower() in table.column_names()]
    if not tables:
        return ""
    listed = ", ".join(f"'{table}'" for table in tables)
    return f" It exists in {listed}; add that table to FROM or a JOIN."


def _find_source(scope: Scope, name: str) -> exp.Table | Scope | None:
    current: Scope | None = scope
    lowered = name.lower()
    while current is not None:
        for source_name, source in current.sources.items():
            if source_name.lower() == lowered:
                return source
        current = current.parent
    return None


def _output_aliases(expression: exp.Expression) -> set[str]:
    """Aliases defined in a SELECT list; DuckDB lets ORDER BY, GROUP BY, and HAVING use them."""
    if not isinstance(expression, exp.Query):
        return set()
    return {select.alias for select in expression.selects if isinstance(select, exp.Alias)}


def _visible_sources(scope: Scope) -> set[str]:
    names: set[str] = set()
    current: Scope | None = scope
    while current is not None:
        names.update(current.sources)
        current = current.parent
    return names


def _source_columns(source: object, schema: DatabaseSchema) -> set[str] | None:
    """Columns a FROM source exposes, or None when they can't be determined statically."""
    if isinstance(source, exp.Table):
        table = schema.table(source.name)
        return {column.name for column in table.columns} if table else None
    if isinstance(source, Scope) and isinstance(source.expression, exp.Query):
        selects = source.expression.named_selects
        if "*" in selects or any(
            isinstance(select, exp.Star)
            or (isinstance(select, exp.Column) and isinstance(select.this, exp.Star))
            for select in source.expression.selects
        ):
            return None
        return set(selects)
    return None


def suggest(name: str, options: list[str], plural: bool = False) -> list[str]:
    """Likely intended identifiers, best first: typo matches, then prefix/suffix matches."""
    lowered = name.lower()
    by_lower = {option.lower(): option for option in options}
    matches: list[str] = []
    if plural:
        for variant in (lowered + "s", lowered.removesuffix("s")):
            if variant in by_lower:
                matches.append(by_lower[variant])
    matches += [
        by_lower[match]
        for match in difflib.get_close_matches(lowered, list(by_lower), n=3, cutoff=0.8)
    ]
    matches += [
        original
        for option, original in by_lower.items()
        if lowered.endswith("_" + option)
        or option.endswith("_" + lowered)
        or lowered.startswith(option + "_")
    ]
    return list(dict.fromkeys(matches))


def apply_row_limit(expression: exp.Query, row_limit: int) -> exp.Query:
    """Push a LIMIT into the query unless it already has a smaller constant one."""
    existing = expression.args.get("limit")
    if isinstance(existing, exp.Limit):
        value = existing.expression
        if isinstance(value, exp.Literal) and value.is_int and int(value.name) <= row_limit:
            return expression
    return expression.limit(row_limit)


def _names(schema: DatabaseSchema) -> set[str]:
    return {table.name for table in schema.tables}


def _hint(candidates: list[str]) -> str:
    return f" Did you mean '{candidates[0]}'?" if candidates else ""


def _first_line(error: Exception) -> str:
    return str(error).strip().splitlines()[0][:300]
