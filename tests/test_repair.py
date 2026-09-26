import pytest

from nl_to_sql_agent.guard import check_sql
from nl_to_sql_agent.repair import autofix_identifiers


@pytest.mark.parametrize(
    "sql, expected",
    [
        ("SELECT stauts FROM orders", "SELECT status FROM orders"),
        ("SELECT order_status FROM orders", "SELECT status FROM orders"),
        ("SELECT c.customer_name FROM customers AS c", "SELECT c.name FROM customers AS c"),
        ("SELECT SUM(price) FROM products", "SELECT SUM(unit_price) FROM products"),
        # Renamed tables keep the old name as an alias, so qualified columns still resolve.
        (
            "SELECT customer.name FROM customer",
            "SELECT customer.name FROM customers AS customer",
        ),
        # Table and column fixes combine in one pass.
        ("SELECT customer_name FROM customer", "SELECT name FROM customers AS customer"),
    ],
)
def test_autofix_repairs_unambiguous_identifiers(sql: str, expected: str, schema) -> None:
    fixed = autofix_identifiers(sql, schema)

    assert fixed == expected
    assert check_sql(fixed, schema).ok


def test_autofix_regression_does_not_corrupt_valid_names(schema) -> None:
    # The old string-replace repair turned total_amount into total_total_amount.
    assert autofix_identifiers("SELECT unit_price FROM products", schema) is None


def test_autofix_leaves_ambiguous_names_alone(schema) -> None:
    # customers.name and products.name both match, so the LLM has to decide.
    sql = (
        "SELECT customer_name FROM customers "
        "JOIN orders USING (customer_id) JOIN order_items USING (order_id) "
        "JOIN products USING (product_id)"
    )

    assert autofix_identifiers(sql, schema) is None


def test_autofix_ignores_unsafe_and_unparseable_sql(schema) -> None:
    assert autofix_identifiers("DROP TABLE customer", schema) is None
    assert autofix_identifiers("SELECT FROM WHERE", schema) is None
