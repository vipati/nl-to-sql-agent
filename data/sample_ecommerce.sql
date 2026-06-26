CREATE TABLE customers (
    customer_id INTEGER PRIMARY KEY,
    name VARCHAR,
    email VARCHAR
);

CREATE TABLE orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER,
    status VARCHAR,
    total_amount DOUBLE,
    created_at TIMESTAMP
);

INSERT INTO customers (customer_id, name, email) VALUES
    (1, 'Avery Chen', 'avery@example.com'),
    (2, 'Jordan Patel', 'jordan@example.com'),
    (3, 'Morgan Rivera', 'morgan@example.com');

INSERT INTO orders (order_id, customer_id, status, total_amount, created_at) VALUES
    (101, 1, 'completed', 120.50, '2026-01-04 10:15:00'),
    (102, 1, 'refunded', 35.00, '2026-01-10 13:40:00'),
    (103, 2, 'completed', 250.00, '2026-01-12 09:05:00'),
    (104, 2, 'pending', 80.25, '2026-01-16 16:20:00'),
    (105, 3, 'completed', 42.75, '2026-01-20 11:30:00');

