## DEF-001: POST /api/shipments answers 500 when the weight exceeds 1000kg

status: open
slug: post-api-shipments-weight-limit
severity: medium
category: error-handling
entry_point: POST /api/shipments
scenario: rejects a shipment over the weight limit
evidence: the scenario expected 400 and the application answered 500
root_cause: ShipmentService throws IllegalArgumentException and nothing maps it to a status
suggested_fix: map the business-rule failure to 400 with a problem-details body
