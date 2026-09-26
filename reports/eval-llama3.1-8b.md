## NL-to-SQL evaluation: openai (llama3.1:8b)

| Metric | Result |
| --- | --- |
| Questions | 28 |
| **Execution accuracy** (extra columns allowed) | **64%** |
| Execution accuracy, strict (exact columns) | 39% |
| Accuracy on first attempt (no repair) | 61% |
| Correct only after a repair | 1 |
| Valid SQL rate (passed guard and executed) | 93% |
| Questions answered (not declined) | 100% |
| Generated SQL blocked as unsafe | 0 |
| Accuracy by difficulty | easy 90%, medium 70%, hard 25% |
| Latency p50 / p95 (end to end) | 2.85 s / 8.52 s |
| Mean model calls per question | 1.14 |
| Mean prompt / completion tokens per question | 444 / 47 |

### Safety suite

| Metric | Result |
| --- | --- |
| Unsafe statements blocked by the guard | 30 / 30 |
| Safe statements allowed by the guard | 10 / 10 |
| Unsafe statements the read-only engine rejects on its own | 24 / 30 |

### Per-question results

| Question | Difficulty | Status | Correct | Attempts | Latency |
| --- | --- | --- | --- | --- | --- |
| How many customers are there? | easy | provider_error | no | 0 | 62.15 s |
| Which customers are from Canada? | easy | ok | yes (extra cols) | 1 | 7.68 s |
| List all product categories. | easy | ok | yes | 1 | 2.30 s |
| How many orders are there in each status? | easy | ok | yes | 1 | 2.68 s |
| What is the most expensive product? | easy | ok | yes (extra cols) | 1 | 2.58 s |
| How many customers do we have in each country? | easy | ok | yes | 1 | 2.65 s |
| Which books cost less than $40? | easy | ok | yes | 1 | 2.56 s |
| What is the average list price of products in each category? | easy | ok | yes | 1 | 2.62 s |
| How many customers signed up in 2025? | easy | ok | yes | 1 | 2.76 s |
| How many orders were placed in March 2025? | easy | ok | yes | 1 | 2.79 s |
| What is our total revenue? | medium | ok | yes | 1 | 2.86 s |
| What is the total revenue for each product category? | medium | ok | yes | 1 | 3.42 s |
| Who are the top 5 customers by total spend? | medium | ok | yes (extra cols) | 1 | 3.49 s |
| How many orders came from each country? | medium | ok | yes | 1 | 2.79 s |
| How many units of each product have been sold in completed orders? | medium | ok | no | 1 | 3.00 s |
| Show 2025 revenue by month number (1 to 12), in month order. | medium | ok | no | 1 | 3.54 s |
| What is the average order value of completed orders? | medium | ok | no | 1 | 2.85 s |
| Which products have never been ordered? | medium | ok | yes (extra cols) | 1 | 2.73 s |
| Which customers have never placed an order? | medium | ok | yes (extra cols) | 1 | 2.77 s |
| Which customers have had at least one order refunded? | medium | ok | yes (extra cols) | 1 | 2.79 s |
| What percentage of all orders were cancelled or refunded? Return a number between 0 and 100. | hard | invalid | no | 3 | 8.52 s |
| For each category, which product sold the most units in completed orders? Include ties. | hard | ok | no | 1 | 3.51 s |
| How many customers have bought products from at least three different categories in completed orders? | hard | ok | no | 1 | 3.51 s |
| Which country has the highest revenue per customer, counting only customers who placed a completed order? | hard | ok | no | 1 | 3.61 s |
| How many order line items were sold below the product's current list price? | hard | ok | yes | 2 | 5.36 s |
| How many customers placed more than 5 orders? | hard | ok | no | 1 | 2.78 s |
| Which completed order had the highest total value, and who placed it? | hard | ok | yes (extra cols) | 1 | 3.41 s |
| For each customer who has ordered, what was the date of their first order? | hard | ok | no | 2 | 5.63 s |
