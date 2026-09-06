## DEF-001: POST /api/orders answers 500 when the quantity exceeds 500

status: open
slug: post-api-orders-quantity-limit
severity: medium
category: error-handling
entry_point: POST /api/orders
scenario: rejects an order over the quantity limit
evidence: the scenario expected 422 and the application answered 500
root_cause: service.create_order raises RuntimeError and nothing maps it to a status
suggested_fix: map the business-rule failure to 422 with a structured error body
