from pydantic import BaseModel


class Column(BaseModel):
    name: str
    data_type: str
    description: str | None = None


class Table(BaseModel):
    name: str
    columns: list[Column]
    description: str | None = None


class DatabaseSchema(BaseModel):
    dialect: str = "duckdb"
    tables: list[Table]


def ecommerce_schema() -> DatabaseSchema:
    return DatabaseSchema(
        tables=[
            Table(
                name="customers",
                description="Registered customers.",
                columns=[
                    Column(name="customer_id", data_type="INTEGER"),
                    Column(name="name", data_type="VARCHAR"),
                    Column(name="email", data_type="VARCHAR"),
                ],
            ),
            Table(
                name="orders",
                description="Customer purchase orders.",
                columns=[
                    Column(name="order_id", data_type="INTEGER"),
                    Column(name="customer_id", data_type="INTEGER"),
                    Column(name="status", data_type="VARCHAR"),
                    Column(name="total_amount", data_type="DOUBLE"),
                    Column(name="created_at", data_type="TIMESTAMP"),
                ],
            ),
        ]
    )

