## NL-to-SQL evaluation: rules

| Metric | Result |
| --- | --- |
| Questions | 28 |
| **Execution accuracy** (extra columns allowed) | **43%** |
| Execution accuracy, strict (exact columns) | 39% |
| Accuracy on first attempt (no repair) | 43% |
| Correct only after a repair | 0 |
| Valid SQL rate (passed guard and executed) | 61% |
| Questions answered (not declined) | 61% |
| Generated SQL blocked as unsafe | 0 |
| Accuracy by difficulty | easy 60%, medium 60%, hard 0% |
| Latency p50 / p95 (end to end) | 17.9 ms / 21.9 ms |
| Mean model calls per question | 1.00 |
| Mean prompt / completion tokens per question | 0 / 0 |

### Safety suite

| Metric | Result |
| --- | --- |
| Unsafe statements blocked by the guard | 30 / 30 |
| Safe statements allowed by the guard | 10 / 10 |
| Unsafe statements the read-only engine rejects on its own | 24 / 30 |

### Per-question results

| Question | Difficulty | Status | Correct | Attempts | Latency |
| --- | --- | --- | --- | --- | --- |
| How many customers are there? | easy | ok | yes | 1 | 43.5 ms |
| Which customers are from Canada? | easy | unanswerable | no | 0 | 0.1 ms |
| List all product categories. | easy | ok | yes | 1 | 20.5 ms |
| How many orders are there in each status? | easy | ok | yes | 1 | 21.3 ms |
| What is the most expensive product? | easy | ok | yes (extra cols) | 1 | 18.7 ms |
| How many customers do we have in each country? | easy | ok | yes | 1 | 20.8 ms |
| Which books cost less than $40? | easy | unanswerable | no | 0 | 0.1 ms |
| What is the average list price of products in each category? | easy | unanswerable | no | 0 | 0.1 ms |
| How many customers signed up in 2025? | easy | ok | no | 1 | 18.3 ms |
| How many orders were placed in March 2025? | easy | ok | yes | 1 | 19.1 ms |
| What is our total revenue? | medium | ok | yes | 1 | 20.1 ms |
| What is the total revenue for each product category? | medium | ok | yes | 1 | 21.0 ms |
| Who are the top 5 customers by total spend? | medium | ok | yes | 1 | 21.9 ms |
| How many orders came from each country? | medium | unanswerable | no | 0 | 0.1 ms |
| How many units of each product have been sold in completed orders? | medium | unanswerable | no | 0 | 0.1 ms |
| Show 2025 revenue by month number (1 to 12), in month order. | medium | ok | no | 1 | 21.1 ms |
| What is the average order value of completed orders? | medium | ok | yes | 1 | 19.6 ms |
| Which products have never been ordered? | medium | ok | yes | 1 | 18.0 ms |
| Which customers have never placed an order? | medium | ok | yes | 1 | 17.9 ms |
| Which customers have had at least one order refunded? | medium | unanswerable | no | 0 | 0.2 ms |
| What percentage of all orders were cancelled or refunded? Return a number between 0 and 100. | hard | unanswerable | no | 0 | 0.2 ms |
| For each category, which product sold the most units in completed orders? Include ties. | hard | unanswerable | no | 0 | 0.1 ms |
| How many customers have bought products from at least three different categories in completed orders? | hard | ok | no | 1 | 17.0 ms |
| Which country has the highest revenue per customer, counting only customers who placed a completed order? | hard | ok | no | 1 | 21.8 ms |
| How many order line items were sold below the product's current list price? | hard | unanswerable | no | 0 | 0.1 ms |
| How many customers placed more than 5 orders? | hard | ok | no | 1 | 16.4 ms |
| Which completed order had the highest total value, and who placed it? | hard | unanswerable | no | 0 | 0.1 ms |
| For each customer who has ordered, what was the date of their first order? | hard | unanswerable | no | 0 | 0.1 ms |
