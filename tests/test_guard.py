import pytest

from nl_to_sql_agent.evaluation import load_safety_cases
from nl_to_sql_agent.guard import check_sql, suggest
from nl_to_sql_agent.schema import DatabaseSchema

SAFETY_CASES = load_safety_cases()


@pytest.mark.parametrize("case", SAFETY_CASES, ids=[case.id for case in SAFETY_CASES])
def test_safety_suite(case, schema: DatabaseSchema) -> None:
    result = check_sql(case.sql, schema)

    assert result.ok is (case.expect == "allowed"), result.error


@pytest.mark.parametrize(
    "sql, message",
    [
        ("DROP TABLE customers", "found DROP"),
        ("SELECT 1; DELETE FROM orders", "Exactly one statement"),
        ("SELECT * FROM read_csv('x.csv')", "read_csv"),
        ("SELECT * FROM range(10)", "Table functions are not allowed"),
        ("SELECT * FROM information_schema.tables", "application schema"),
        ("   ", "Empty SQL"),
        ("SELECT " + "1 + " * 5000 + "1", "longer than"),
    ],
)
def test_unsafe_sql_is_rejected_with_reason(sql: str, message: str, schema) -> None:
    result = check_sql(sql, schema)

    assert result.error_kind == "unsafe"
    assert message in result.error


def test_syntax_errors_are_classified(schema) -> None:
    result = check_sql("SELECT FROM WHERE", schema)

    assert result.error_kind == "syntax"


@pytest.mark.parametrize(
    "sql, message",
    [
        ("SELECT * FROM customer", "Table 'customer' does not exist. Did you mean 'customers'?"),
        ("SELECT stauts FROM orders", "Did you mean 'status'?"),
        ("SELECT c.customer_name FROM customers c", "does not exist in 'customers'"),
        ("SELECT x.name FROM customers", "unknown table or alias 'x'"),
    ],
)
def test_unknown_identifiers_are_schema_errors_with_hints(sql: str, message: str, schema) -> None:
    result = check_sql(sql, schema)

    assert result.error_kind == "schema"
    assert message in result.error


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT status AS s, COUNT(*) AS n FROM orders GROUP BY s ORDER BY n DESC",
        "WITH t AS (SELECT customer_id, COUNT(*) AS n FROM orders GROUP BY 1) "
        "SELECT c.name, t.n FROM t JOIN customers c USING (customer_id)",
        "SELECT name FROM customers c WHERE EXISTS "
        "(SELECT 1 FROM orders o WHERE o.customer_id = c.customer_id)",
        "SELECT * FROM (SELECT name, country FROM customers) AS sub WHERE country = 'UK'",
        "SELECT list_transform([1, 2], x -> x + 1)",
        "SELECT main.customers.name FROM main.customers",
    ],
)
def test_valid_queries_pass(sql: str, schema) -> None:
    result = check_sql(sql, schema)

    assert result.ok, result.error


def test_cte_columns_are_checked(schema) -> None:
    sql = "WITH t AS (SELECT customer_id FROM orders) SELECT t.missing FROM t"

    result = check_sql(sql, schema)

    assert result.error_kind == "schema"
    assert "'missing'" in result.error


def test_row_limit_is_pushed_down(schema) -> None:
    assert check_sql("SELECT name FROM customers", schema, row_limit=11).sql.endswith("LIMIT 11")
    assert check_sql("SELECT name FROM customers LIMIT 5000", schema, row_limit=11).sql.endswith(
        "LIMIT 11"
    )
    assert check_sql("SELECT name FROM customers LIMIT 3", schema, row_limit=11).sql.endswith(
        "LIMIT 3"
    )


def test_executed_sql_is_rendered_from_the_checked_ast(schema) -> None:
    result = check_sql("select name from customers -- trailing comment", schema)

    assert result.ok
    assert result.sql == "SELECT name FROM customers /* trailing comment */"
    assert result.tables == ["customers"]


def test_suggest_prefers_typos_and_affixes() -> None:
    columns = ["customer_id", "name", "status", "unit_price"]

    assert suggest("stauts", columns) == ["status"]
    assert suggest("customer_name", columns) == ["name"]
    assert suggest("price", columns) == ["unit_price"]
    assert suggest("customer", ["customers", "orders"], plural=True) == ["customers"]
    assert suggest("zzz", columns) == []
