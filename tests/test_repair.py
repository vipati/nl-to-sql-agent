from nl_to_sql_agent.repair import execute_with_repair, repair_sql


def test_repair_sql_fixes_known_schema_typos() -> None:
    sql = "SELECT customer_name, SUM(amount) FROM orders JOIN customer USING (customer_id)"

    repaired = repair_sql(sql)

    assert "customer_name" not in repaired
    assert "total_amount" in repaired
    assert "customers" in repaired


def test_execute_with_repair_recovers_from_missing_column() -> None:
    attempt = execute_with_repair(
        "SELECT customers.customer_name, SUM(orders.amount) AS total_revenue "
        "FROM orders "
        "JOIN customers ON orders.customer_id = customers.customer_id "
        "GROUP BY customers.customer_name "
        "ORDER BY total_revenue DESC"
    )

    assert attempt.changed is True
    assert attempt.executed is True
    assert attempt.execution is not None
    assert attempt.execution.rows[0]["name"] == "Jordan Patel"

