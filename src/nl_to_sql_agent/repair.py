"""Deterministic repair for wrong identifiers, tried before spending an LLM call.

Models often get a name slightly wrong: `customer` for `customers`, `order_status` for
`status`, `stauts` for `status`. When the guard finds an unknown table or column and the
schema offers exactly one plausible replacement, the name is rewritten in the AST.
Anything ambiguous is left for the LLM repair step.
"""

from sqlglot import exp
from sqlglot.errors import SqlglotError

from nl_to_sql_agent.guard import UnsafeSQLError, find_schema_issues, parse_single_query
from nl_to_sql_agent.schema import DatabaseSchema


def autofix_identifiers(sql: str, schema: DatabaseSchema) -> str | None:
    """Return SQL with unambiguous identifier fixes applied, or None if nothing changed."""
    try:
        expression = parse_single_query(sql, schema.dialect)
    except (SqlglotError, UnsafeSQLError):
        return None

    changed = False
    # Two passes: column checks only run once every table name resolves.
    for _ in range(2):
        issues = find_schema_issues(expression, schema)
        fixable = [issue for issue in issues if len(issue.candidates) == 1]
        if not fixable:
            break
        for issue in fixable:
            replacement = issue.candidates[0]
            node = issue.node
            if isinstance(node, exp.Table):
                if not node.alias:
                    # Keep the old name as an alias so qualified references still resolve.
                    node.set("alias", exp.TableAlias(this=exp.to_identifier(node.name)))
                node.set("this", exp.to_identifier(replacement))
            elif isinstance(node, exp.Column):
                qualifier, _, column = replacement.rpartition(".")
                node.set("this", exp.to_identifier(column))
                if qualifier:
                    node.set("table", exp.to_identifier(qualifier))
        changed = True
    return expression.sql(dialect=schema.dialect) if changed else None
