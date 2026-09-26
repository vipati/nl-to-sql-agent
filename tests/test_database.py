import duckdb
import pytest

from nl_to_sql_agent.database import Database, QueryTimeoutError, sample_database_path
from nl_to_sql_agent.schema import format_schema_context


def test_execute_returns_json_friendly_rows(database: Database) -> None:
    result = database.execute(
        "SELECT status, COUNT(*) AS n, SUM(1.50::DECIMAL(10, 2)) AS d, MIN(order_date) AS first "
        "FROM orders GROUP BY status ORDER BY n DESC"
    )

    assert result.columns == ["status", "n", "d", "first"]
    assert result.rows[0] == ["completed", 41, 61.5, "2025-01-17"]
    assert result.truncated is False


def test_duplicate_column_names_are_preserved(database: Database) -> None:
    result = database.execute("SELECT 1 AS x, 2 AS x")

    assert result.columns == ["x", "x"]
    assert result.rows == [[1, 2]]


def test_rows_are_capped() -> None:
    database = Database(sample_database_path(), max_rows=5)

    result = database.execute("SELECT * FROM order_items")

    assert result.row_count == 5
    assert result.truncated is True


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM orders",
        "DROP TABLE customers",
        "CREATE TABLE t (x INTEGER)",
        "SELECT * FROM read_csv('data/sample_ecommerce.sql')",
        "COPY customers TO 'leak.csv'",
        "SET enable_external_access = true",
    ],
)
def test_engine_rejects_writes_and_file_access_without_the_guard(
    sql: str, database: Database
) -> None:
    # Defense in depth: these reach the engine directly, bypassing the SQL guard.
    with pytest.raises(duckdb.Error):
        database.execute(sql)


def test_slow_queries_are_cancelled() -> None:
    database = Database(sample_database_path(), timeout_seconds=0.2)
    cross_join = "SELECT COUNT(*) FROM order_items a, order_items b, order_items c, order_items d"

    with pytest.raises(QueryTimeoutError, match="timeout"):
        database.execute(cross_join + " WHERE a.quantity + b.quantity + c.quantity > d.quantity")


def test_missing_database_file_is_reported(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        Database(tmp_path / "missing.duckdb")


def test_schema_is_introspected_with_keys_comments_and_values(database: Database) -> None:
    schema = database.schema
    orders = schema.table("orders")

    assert schema.table_names() == {"customers", "orders", "order_items", "products"}
    assert orders is not None
    assert "completed" in orders.description
    columns = {column.name: column for column in orders.columns}
    assert columns["order_id"].primary_key
    assert columns["customer_id"].references == "customers.customer_id"
    assert columns["status"].sample_values == ["cancelled", "completed", "pending", "refunded"]


def test_schema_context_is_commented_ddl(database: Database) -> None:
    context = format_schema_context(database.schema)

    assert "CREATE TABLE orders (" in context
    assert "customer_id INTEGER REFERENCES customers(customer_id)" in context
    assert "values: 'cancelled', 'completed', 'pending', 'refunded'" in context
    # Names and emails are high-cardinality personal data; they are never sampled.
    assert "@example.com" not in context


def test_user_database_file(tmp_path) -> None:
    path = tmp_path / "custom.duckdb"
    connection = duckdb.connect(str(path))
    connection.execute("CREATE TABLE events (id INTEGER, kind VARCHAR)")
    connection.execute("INSERT INTO events VALUES (1, 'click'), (2, 'view')")
    connection.close()

    database = Database(path)

    assert database.schema.table("events").column_names() == {"id", "kind"}
    assert database.execute("SELECT COUNT(*) FROM events").rows == [[2]]
