## NL-to-SQL evaluation: openai (llama3.1:8b)

| Metric | Result |
| --- | --- |
| Questions | 28 |
| **Execution accuracy** (extra columns allowed) | **68%** |
| Execution accuracy, strict (exact columns) | 43% |
| Accuracy on first attempt (no repair) | 64% |
| Correct only after a repair | 1 |
| Valid SQL rate (passed guard and executed) | 100% |
| Questions answered (not declined) | 100% |
| Generated SQL blocked as unsafe | 0 |
| Accuracy by difficulty | easy 100%, medium 70%, hard 25% |
| Latency p50 / p95 (end to end) | 2.79 s / 5.61 s |
| Mean model calls per question | 1.11 |
| Mean prompt / completion tokens per question | 442 / 46 |

### Safety suite

| Metric | Result |
| --- | --- |
| Unsafe statements blocked by the guard | 30 / 30 |
| Safe statements allowed by the guard | 10 / 10 |
| Unsafe statements the read-only engine rejects on its own | 24 / 30 |

### Per-question results

| Question | Difficulty | Status | Correct | Attempts | Latency |
| --- | --- | --- | --- | --- | --- |
| How many customers are there? | easy | ok | yes | 1 | 2.52 s |
| Which customers are from Canada? | easy | ok | yes (extra cols) | 1 | 2.53 s |
| List all product categories. | easy | ok | yes | 1 | 2.18 s |
| How many orders are there in each status? | easy | ok | yes | 1 | 2.53 s |
| What is the most expensive product? | easy | ok | yes (extra cols) | 1 | 2.60 s |
| How many customers do we have in each country? | easy | ok | yes | 1 | 2.61 s |
| Which books cost less than $40? | easy | ok | yes | 1 | 2.58 s |
| What is the average list price of products in each category? | easy | ok | yes | 1 | 2.65 s |
| How many customers signed up in 2025? | easy | ok | yes | 1 | 2.76 s |
| How many orders were placed in March 2025? | easy | ok | yes | 1 | 2.70 s |
| What is our total revenue? | medium | ok | yes | 1 | 2.86 s |
| What is the total revenue for each product category? | medium | ok | yes | 1 | 3.32 s |
| Who are the top 5 customers by total spend? | medium | ok | yes (extra cols) | 1 | 3.46 s |
| How many orders came from each country? | medium | ok | yes | 1 | 2.77 s |
| How many units of each product have been sold in completed orders? | medium | ok | no | 1 | 2.98 s |
| Show 2025 revenue by month number (1 to 12), in month order. | medium | ok | no | 1 | 3.53 s |
| What is the average order value of completed orders? | medium | ok | no | 1 | 2.84 s |
| Which products have never been ordered? | medium | ok | yes (extra cols) | 1 | 2.77 s |
| Which customers have never placed an order? | medium | ok | yes (extra cols) | 1 | 2.74 s |
| Which customers have had at least one order refunded? | medium | ok | yes (extra cols) | 1 | 2.69 s |
| What percentage of all orders were cancelled or refunded? Return a number between 0 and 100. | hard | ok | no | 2 | 5.89 s |
| For each category, which product sold the most units in completed orders? Include ties. | hard | ok | no | 1 | 3.35 s |
| How many customers have bought products from at least three different categories in completed orders? | hard | ok | no | 1 | 3.49 s |
| Which country has the highest revenue per customer, counting only customers who placed a completed order? | hard | ok | no | 1 | 3.73 s |
| How many order line items were sold below the product's current list price? | hard | ok | yes | 2 | 5.37 s |
| How many customers placed more than 5 orders? | hard | ok | no | 1 | 2.81 s |
| Which completed order had the highest total value, and who placed it? | hard | ok | yes (extra cols) | 1 | 3.43 s |
| For each customer who has ordered, what was the date of their first order? | hard | ok | no | 2 | 5.61 s |
