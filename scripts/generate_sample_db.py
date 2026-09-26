"""Regenerate data/sample_ecommerce.sql deterministically.

The committed SQL file is the source of truth; this script documents how it was made
and lets the dataset be resized without hand-editing INSERT statements.

    uv run python scripts/generate_sample_db.py
"""

import random
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

OUTPUT = Path(__file__).resolve().parents[1] / "data" / "sample_ecommerce.sql"
SEED = 42

CUSTOMERS = [
    ("Avery Chen", "USA"),
    ("Jordan Patel", "USA"),
    ("Morgan Rivera", "USA"),
    ("Riley Thompson", "USA"),
    ("Sam Okafor", "Canada"),
    ("Casey Martin", "Canada"),
    ("Taylor Nguyen", "Canada"),
    ("Jamie Walsh", "UK"),
    ("Alex Brooks", "UK"),
    ("Robin Weber", "Germany"),
    ("Kai Fischer", "Germany"),
    ("Priya Sharma", "India"),
]
# Customers who sign up but never order, so "customers without orders" has an answer.
INACTIVE_CUSTOMERS = {"Riley Thompson", "Kai Fischer"}

PRODUCTS = [
    ("Wireless Mouse", "Electronics", "24.99"),
    ("Mechanical Keyboard", "Electronics", "89.00"),
    ("USB-C Hub", "Electronics", "39.50"),
    ("Noise-Cancelling Headphones", "Electronics", "199.00"),
    ("Designing Data-Intensive Applications", "Books", "45.00"),
    ("The Pragmatic Programmer", "Books", "39.99"),
    ("Clean Architecture", "Books", "34.50"),
    ("Pour-Over Coffee Kit", "Home", "32.00"),
    ("Desk Lamp", "Home", "27.75"),
    ("Standing Desk Mat", "Home", "49.00"),
    ("Yoga Mat", "Sports", "25.00"),
    ("Resistance Bands", "Sports", "18.50"),
    ("Foam Roller", "Sports", "21.00"),
]
# Never ordered, so "products that have never been ordered" has an answer.
UNSOLD_PRODUCTS = {"Foam Roller"}

STATUSES = ["completed"] * 7 + ["pending", "cancelled", "refunded"]
ORDER_COUNT = 60

SCHEMA = """\
CREATE TABLE customers (
    customer_id INTEGER PRIMARY KEY,
    name VARCHAR NOT NULL,
    email VARCHAR NOT NULL,
    country VARCHAR NOT NULL,
    signup_date DATE NOT NULL
);

CREATE TABLE products (
    product_id INTEGER PRIMARY KEY,
    name VARCHAR NOT NULL,
    category VARCHAR NOT NULL,
    unit_price DECIMAL(10, 2) NOT NULL
);

CREATE TABLE orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers (customer_id),
    order_date DATE NOT NULL,
    status VARCHAR NOT NULL
);

CREATE TABLE order_items (
    order_id INTEGER NOT NULL REFERENCES orders (order_id),
    product_id INTEGER NOT NULL REFERENCES products (product_id),
    quantity INTEGER NOT NULL,
    unit_price DECIMAL(10, 2) NOT NULL
);

COMMENT ON TABLE customers IS 'Registered customers, one row per customer.';
COMMENT ON COLUMN customers.name IS 'Customer full name.';
COMMENT ON COLUMN customers.signup_date IS 'Date the customer created an account.';
COMMENT ON TABLE products IS 'Product catalog.';
COMMENT ON COLUMN products.unit_price IS 'Current list price in USD.';
COMMENT ON TABLE orders IS
    'One row per order. Revenue and sales only count orders with status ''completed''.';
COMMENT ON COLUMN orders.order_date IS 'Date the order was placed.';
COMMENT ON TABLE order_items IS 'Line items. Line revenue is quantity * unit_price.';
COMMENT ON COLUMN order_items.unit_price IS
    'Price actually paid per unit in USD, after any discount.';
"""


def sql_literal(value: object) -> str:
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    if isinstance(value, date):
        return f"DATE '{value.isoformat()}'"
    return str(value)


def insert(table: str, columns: list[str], rows: list[tuple]) -> str:
    values = ",\n".join("    (" + ", ".join(sql_literal(v) for v in row) + ")" for row in rows)
    return f"INSERT INTO {table} ({', '.join(columns)}) VALUES\n{values};\n"


def main() -> None:
    rng = random.Random(SEED)

    customers = []
    for customer_id, (name, country) in enumerate(CUSTOMERS, start=1):
        email = name.lower().replace(" ", ".") + "@example.com"
        signup = date(2024, 1, 1) + timedelta(days=rng.randrange(0, 540))
        customers.append((customer_id, name, email, country, signup))

    products = [
        (product_id, name, category, Decimal(price))
        for product_id, (name, category, price) in enumerate(PRODUCTS, start=1)
    ]

    active = [c for c in customers if c[1] not in INACTIVE_CUSTOMERS]
    sellable = [p for p in products if p[1] not in UNSOLD_PRODUCTS]
    placed = []
    for _ in range(ORDER_COUNT):
        customer = rng.choice(active)
        first_day = max(customer[4], date(2025, 1, 1))
        days_left = (date(2025, 12, 31) - first_day).days
        placed.append((first_day + timedelta(days=rng.randrange(0, days_left + 1)), customer[0]))
    placed.sort()

    orders = []
    items = []
    for order_id, (order_date, customer_id) in enumerate(placed, start=1001):
        orders.append((order_id, customer_id, order_date, rng.choice(STATUSES)))
        for product in rng.sample(sellable, rng.randint(1, 3)):
            price = float(product[3])
            if rng.random() < 0.15:
                price *= 0.9  # occasional 10% discount
            items.append((order_id, product[0], rng.randint(1, 3), Decimal(f"{price:.2f}")))

    parts = [
        "-- Generated by scripts/generate_sample_db.py. Do not edit by hand.\n",
        SCHEMA,
        insert("customers", ["customer_id", "name", "email", "country", "signup_date"], customers),
        insert("products", ["product_id", "name", "category", "unit_price"], products),
        insert("orders", ["order_id", "customer_id", "order_date", "status"], orders),
        insert("order_items", ["order_id", "product_id", "quantity", "unit_price"], items),
    ]
    OUTPUT.write_text("\n".join(parts), encoding="utf-8", newline="\n")
    print(f"Wrote {OUTPUT} ({len(customers)} customers, {len(orders)} orders, {len(items)} items)")


if __name__ == "__main__":
    main()
