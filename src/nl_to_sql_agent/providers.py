from abc import ABC, abstractmethod
from dataclasses import dataclass

from nl_to_sql_agent.schema import DatabaseSchema


@dataclass(frozen=True)
class GenerationPrompt:
    question: str
    schema_context: str


class SQLGenerationProvider(ABC):
    @abstractmethod
    def generate(self, prompt: GenerationPrompt) -> str:
        """Generate SQL from a question and schema context."""


class DeterministicProvider(SQLGenerationProvider):
    """Local provider used for tests and demos without external API keys."""

    def generate(self, prompt: GenerationPrompt) -> str:
        normalized = prompt.question.lower().strip()

        if "revenue" in normalized and "customer" in normalized:
            return (
                "SELECT customers.name, SUM(orders.total_amount) AS total_revenue "
                "FROM orders "
                "JOIN customers ON orders.customer_id = customers.customer_id "
                "GROUP BY customers.name "
                "ORDER BY total_revenue DESC"
            )

        if "orders" in normalized and ("status" in normalized or "count" in normalized):
            return (
                "SELECT status, COUNT(*) AS order_count "
                "FROM orders "
                "GROUP BY status "
                "ORDER BY order_count DESC"
            )

        if "customers" in normalized or "customer" in normalized:
            return "SELECT customer_id, name, email FROM customers ORDER BY name"

        raise ValueError("Provider could not generate SQL for this question.")


def build_prompt(question: str, schema: DatabaseSchema) -> GenerationPrompt:
    return GenerationPrompt(question=question, schema_context=format_schema_context(schema))


def format_schema_context(schema: DatabaseSchema) -> str:
    table_blocks: list[str] = []
    for table in schema.tables:
        columns = ", ".join(f"{column.name} {column.data_type}" for column in table.columns)
        table_blocks.append(f"{table.name}({columns})")
    return "\n".join(table_blocks)

