## DEF-001: POST /api/deals answers 500 when the quantity exceeds 10000

status: open
slug: post-api-deals-quantity-limit
severity: medium
category: error-handling
entry_point: POST /api/deals
scenario: rejects a deal over the quantity limit
evidence: the scenario expected 400 and the application answered 500
root_cause: DealService throws InvalidOperationException and nothing maps it to a status
suggested_fix: map the business-rule failure to 400 with a problem-details body
