import json
import re
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from nl_to_sql_agent.config import Settings
from nl_to_sql_agent.schema import DatabaseSchema, format_schema_context


class ProviderError(RuntimeError):
    """The model backend failed or returned something unusable."""


class UnanswerableError(ValueError):
    """The provider cannot produce SQL for this question."""


@dataclass(frozen=True)
class GenerationRequest:
    question: str
    schema: DatabaseSchema
    schema_context: str
    # Set when asking the model to fix its previous attempt.
    previous_sql: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class Generation:
    sql: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class SQLProvider(Protocol):
    name: str

    def generate(self, request: GenerationRequest) -> Generation: ...


def build_request(
    question: str,
    schema: DatabaseSchema,
    previous_sql: str | None = None,
    error: str | None = None,
) -> GenerationRequest:
    return GenerationRequest(
        question=question,
        schema=schema,
        schema_context=format_schema_context(schema),
        previous_sql=previous_sql,
        error=error,
    )


SYSTEM_PROMPT = """\
You translate questions into one {dialect} SQL query over the database below.

Rules:
- Reply with exactly one read-only SELECT query (CTEs are fine) and nothing else.
- Use only the tables and columns defined below. Join using the REFERENCES relationships.
- Follow the business rules in the comments, for example which orders count as revenue.
- Select only the columns needed to answer the question. Alias computed columns.
- Add ORDER BY when the question asks for a ranking, a top N, or a time series.

Database schema:
{schema}
"""

REPAIR_PROMPT = """\
That query failed:
{error}

Reply with a corrected query only."""


class OpenAICompatibleProvider:
    """Calls any `/chat/completions` API: OpenAI, Ollama, vLLM, LM Studio."""

    name = "openai"

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str = "",
        timeout_seconds: float = 60.0,
    ) -> None:
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.model = model
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def messages(self, request: GenerationRequest) -> list[dict[str, str]]:
        system = SYSTEM_PROMPT.format(
            dialect=request.schema.dialect.capitalize(), schema=request.schema_context
        )
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": request.question},
        ]
        if request.previous_sql is not None:
            messages.append({"role": "assistant", "content": request.previous_sql})
            messages.append(
                {"role": "user", "content": REPAIR_PROMPT.format(error=request.error or "")}
            )
        return messages

    def generate(self, request: GenerationRequest) -> Generation:
        body = json.dumps(
            {"model": self.model, "messages": self.messages(request), "temperature": 0}
        ).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        http_request = urllib.request.Request(self.url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(http_request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            raise ProviderError(f"LLM request to {self.url} failed: {error}") from error

        try:
            text = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise ProviderError(f"Unexpected LLM response: {payload!r:.200}") from error
        usage = payload.get("usage") or {}
        return Generation(
            sql=extract_sql(text or ""),
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
        )


_FENCE = re.compile(r"```[a-zA-Z]*\s*(.*?)```", re.DOTALL)


def extract_sql(text: str) -> str:
    """Pull the query out of a model reply, dropping markdown fences and a trailing semicolon.

    Anything else the model adds (prose, a second statement) is left in place on purpose,
    so the guard rejects it and the repair loop tells the model what went wrong.
    """
    match = _FENCE.search(text)
    sql = match.group(1) if match else text
    return sql.strip().rstrip(";").strip()


_MONTHS = {
    name: index
    for index, name in enumerate(
        ["january", "february", "march", "april", "may", "june", "july", "august",
         "september", "october", "november", "december"],
        start=1,
    )
}  # fmt: skip

_REVENUE = "SUM(order_items.quantity * order_items.unit_price)"
_ORDER_LINES = "FROM orders JOIN order_items ON order_items.order_id = orders.order_id "
Template = str | Callable[[re.Match[str]], str]


def _rule_templates() -> list[tuple[re.Pattern[str], Template]]:
    """Keyword patterns for the bundled ecommerce sample. Ordered from specific to generic."""

    def top_customers(match: re.Match[str]) -> str:
        limit = f" LIMIT {match.group('n')}" if match.group("n") else ""
        return (
            f"SELECT customers.name, {_REVENUE} AS total_spent {_ORDER_LINES}"
            "JOIN customers ON customers.customer_id = orders.customer_id "
            "WHERE orders.status = 'completed' "
            f"GROUP BY customers.name ORDER BY total_spent DESC{limit}"
        )

    def orders_in_month(match: re.Match[str]) -> str:
        month = _MONTHS[match.group("month")]
        year = int(match.group("year"))
        return (
            "SELECT COUNT(*) AS order_count FROM orders "
            f"WHERE year(order_date) = {year} AND month(order_date) = {month}"
        )

    month_names = "|".join(_MONTHS)
    rules: list[tuple[str, Template]] = [
        (
            rf"orders?\b.*\bin (?P<month>{month_names}) (?P<year>\d{{4}})",
            orders_in_month,
        ),
        (
            r"products?\b.*\bnever (been )?(ordered|sold|purchased)",
            "SELECT products.name FROM products WHERE NOT EXISTS ("
            "SELECT 1 FROM order_items WHERE order_items.product_id = products.product_id)",
        ),
        (
            r"customers?\b.*\b(never|no|without|not)\b.*\b(orders?|ordered|purchased)",
            "SELECT customers.name FROM customers WHERE NOT EXISTS ("
            "SELECT 1 FROM orders WHERE orders.customer_id = customers.customer_id)",
        ),
        (
            r"revenue\b.*\b(by|per|for each) (product )?category",
            f"SELECT products.category, {_REVENUE} AS revenue {_ORDER_LINES}"
            "JOIN products ON products.product_id = order_items.product_id "
            "WHERE orders.status = 'completed' "
            "GROUP BY products.category ORDER BY revenue DESC",
        ),
        (
            r"(monthly (revenue|sales)|(revenue|sales)\b.*\b(by|per) month)",
            f"SELECT strftime(orders.order_date, '%Y-%m') AS month, {_REVENUE} AS revenue "
            f"{_ORDER_LINES}WHERE orders.status = 'completed' GROUP BY month ORDER BY month",
        ),
        (
            r"top (?P<n>\d+ )?customers|(revenue|spend|spent)\b.*\b(by|per) customer",
            top_customers,
        ),
        (
            r"(best[- ]selling|top[- ]selling|quantity sold\b.*\b(by|per|for each)) products?",
            "SELECT products.name, SUM(order_items.quantity) AS units_sold "
            f"{_ORDER_LINES}"
            "JOIN products ON products.product_id = order_items.product_id "
            "WHERE orders.status = 'completed' GROUP BY products.name ORDER BY units_sold DESC",
        ),
        (
            r"average order value",
            "SELECT AVG(order_total) AS average_order_value FROM ("
            f"SELECT orders.order_id, {_REVENUE} AS order_total {_ORDER_LINES}"
            "WHERE orders.status = 'completed' GROUP BY orders.order_id)",
        ),
        (
            r"total revenue|how much revenue",
            f"SELECT {_REVENUE} AS total_revenue {_ORDER_LINES}WHERE orders.status = 'completed'",
        ),
        (
            r"orders?\b.*\b(by|per|for each|in each) status|status\b.*\borders",
            "SELECT status, COUNT(*) AS order_count FROM orders "
            "GROUP BY status ORDER BY order_count DESC",
        ),
        (
            r"customers?\b.*\b(by|per|in each|from each) country",
            "SELECT country, COUNT(*) AS customer_count FROM customers "
            "GROUP BY country ORDER BY customer_count DESC",
        ),
        (
            r"most expensive product",
            "SELECT name, unit_price FROM products ORDER BY unit_price DESC LIMIT 1",
        ),
        (
            r"(list|what are|show)\b.*\bcategories",
            "SELECT DISTINCT category FROM products ORDER BY category",
        ),
        (
            r"(how many|number of|count of) customers",
            "SELECT COUNT(*) AS customer_count FROM customers",
        ),
        (
            r"(list|show)( all)? customers",
            "SELECT name, email, country FROM customers ORDER BY name",
        ),
    ]
    return [(re.compile(pattern), template) for pattern, template in rules]


class RulesProvider:
    """Offline keyword-template baseline for the bundled ecommerce sample.

    It needs no model or API key, so tests, CI, and the demo run anywhere. It does not
    understand language: questions outside its templates are declined, not guessed.
    """

    name = "rules"
    _templates = _rule_templates()

    def generate(self, request: GenerationRequest) -> Generation:
        if request.previous_sql is not None:
            raise UnanswerableError("The rules provider cannot repair SQL.")
        required = {"customers", "orders", "order_items", "products"}
        if not required <= request.schema.table_names():
            raise UnanswerableError("The rules provider only knows the bundled sample schema.")

        question = " ".join(request.question.lower().split())
        for pattern, template in self._templates:
            match = pattern.search(question)
            if match:
                sql = template if isinstance(template, str) else template(match)
                return Generation(sql=sql)
        raise UnanswerableError(
            "No rule matches this question. Set NL2SQL_PROVIDER=openai to use an LLM."
        )


def provider_from_settings(settings: Settings) -> SQLProvider:
    if settings.provider == "rules":
        return RulesProvider()
    if settings.provider == "openai":
        return OpenAICompatibleProvider(
            base_url=settings.base_url,
            model=settings.model,
            api_key=settings.api_key,
            timeout_seconds=settings.llm_timeout_seconds,
        )
    raise ValueError(f"Unknown NL2SQL_PROVIDER {settings.provider!r}; use 'rules' or 'openai'")
