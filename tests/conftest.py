from dataclasses import dataclass, field

import pytest

from nl_to_sql_agent.database import Database
from nl_to_sql_agent.providers import Generation, GenerationRequest, UnanswerableError
from nl_to_sql_agent.schema import DatabaseSchema

# About 1.7 trillion row combinations: no machine finishes this before the test timeout.
SLOW_SQL = (
    "SELECT COUNT(*) FROM order_items a, order_items b, order_items c, order_items d, "
    "order_items e, order_items f "
    "WHERE a.quantity + b.quantity + c.quantity + d.quantity + e.quantity > f.quantity * 7"
)


@pytest.fixture(scope="session")
def database() -> Database:
    return Database.sample()


@pytest.fixture(scope="session")
def schema(database: Database) -> DatabaseSchema:
    return database.schema


@dataclass
class ScriptedProvider:
    """Returns queued SQL strings in order and records every request it receives."""

    responses: list[str]
    name: str = "scripted"
    requests: list[GenerationRequest] = field(default_factory=list)

    def generate(self, request: GenerationRequest) -> Generation:
        self.requests.append(request)
        if not self.responses:
            raise UnanswerableError("script exhausted")
        return Generation(sql=self.responses.pop(0), prompt_tokens=100, completion_tokens=20)
