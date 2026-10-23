# Deal Payments and Shipments

This is manual operational recording, not a bank integration or a replacement for accounting. Currency is RUB. Existing calculator rules and manager commission rules are unchanged.

## Routes and Permissions

All routes require bearer authentication. An employee can read/write only their own active deals; administrators/managers can access any active deal. Ownership is rechecked for every request. Database failures return errors rather than zero balances.

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/deals/{dealId}/operations` | Payments, shipments, summary and paginated history |
| POST | `/deals/{dealId}/payments` | Record a payment plan or actual payment |
| PATCH | `/deals/{dealId}/payments/{id}` | Replace editable payment fields |
| POST | `/deals/{dealId}/payments/{id}/cancel` | Cancel an erroneous record with a reason |
| POST | `/deals/{dealId}/shipments` | Plan or confirm a shipment |
| PATCH | `/deals/{dealId}/shipments/{id}` | Replace editable shipment fields |
| POST | `/deals/{dealId}/shipments/{id}/cancel` | Cancel a shipment record with a reason |

GET accepts `historyPage` (default 1) and `historyPageSize` (default 25, maximum 100). History is newest first. The response has `dealId`, `revision`, `version`, `summary`, `payments`, `shipments`, `history`. Financial responses use `Cache-Control: no-store`.

## Versioning and Repeated Requests

Every operation mutation requires the latest opaque 64-character `revision` from GET. A stale revision returns 409; refresh and review the latest balances before resubmitting. Standard deal PATCH also accepts `operationsRevision` from the deal response and requires it after the operations ledger exists. Detail, list and operations responses use the same canonical revision.

Payment/shipment create and PATCH bodies require `requestId`, a client-generated UUID. Reuse the same UUID when retrying an uncertain create response. An identical retried create returns the existing operation, including concurrent duplicates. Reusing a UUID with different create data returns 409. Editable PATCH fields are sent as a complete representation; immutable IDs/audit fields cannot be set through the body.

## Payments

Fields: `revision`, `requestId`, `kind`, `status`, `amount`, `dueDate`, `actualDate`, `reference`, `comment`.

- `kind`: `customer` (incoming), `provider` (outgoing material payment), `delivery` (outgoing transport payment), `other` (other outgoing expense).
- `status`: `planned` or `paid`. Only paid records affect balances.
- `amount`: positive decimal, up to 2 decimal places, maximum 14 digits. A decimal string is supported; storage and summation use integer kopecks.
- `dueDate`: required for plans. `actualDate`: required for paid entries and cannot be in the future in Europe/Moscow. Dates are calendar `YYYY-MM-DD` values.
- `reference`: optional payment document number (100 characters); `comment`: optional (1000 characters).

Cancellation body: `{revision, reason}`; reason is at least 3 and at most 1000 trimmed characters. Cancelled records remain readable and are excluded from totals. They cannot be edited; create a replacement record when appropriate. Cancellation corrects a record, not an actual bank refund.

Customer amount due is the current calculator `totalAmount` minus recorded customer receipts, with overpayments shown separately. Provider amount due uses planned material purchase total minus provider payments. Provider overpayments are also separate. These are order balances, not an invoice/accrual ledger or overdue accounting debt. `cashBalance` is receipts minus recorded payouts, not profit.

## Shipments

Fields: `revision`, `requestId`, `status`, `quantity`, `unit`, `plannedDate`, `actualDate`, `amountPurchase`, `deliveryCost`, `shippingAddressId`, `deliveryAddressId`, `comment`.

- Status is `planned` or `delivered`. Plan date is required for plans; actual date is required for delivered records and cannot be in the future in Europe/Moscow.
- Quantity is positive, at most 3 decimal places and 14 digits. Units normalize tonne, cubic-metre and piece aliases and must match the deal unit. Mixed units are not added together.
- Active planned plus delivered quantity cannot exceed the deal quantity. Concurrent writes are checked atomically. Lowering the order below committed quantities or changing its unit/material/provider while shipments are active is rejected.
- Addresses default to deal addresses and may be selected separately per shipment. New/changed addresses must be active and belong to the corresponding company. Existing archived address references remain in historical records. Address text is snapshotted for new selections.
- `amountPurchase` is the total material cost of that shipment; null uses the existing calculator fallback of quantity times purchase unit price. `deliveryCost` is an optional operational cost field; it does not silently replace the calculator's existing proportional delivery-cost formula.
- Remaining quantity is ordered minus delivered. Unplanned quantity also subtracts active plans. Confirming only part of a plan replaces that plan with the entered actual quantity; schedule a new record for the remaining commitment if needed. The previous planned amount remains in history.

Only delivered, non-cancelled shipment records project into legacy `deliveredQuantity`; therefore the existing calculator continues to work. Standard deal editing no longer writes managed delivery arrays. Payments do not change margin or commission calculations.

## Storage, History and Deployment

The private `_operations` ledger is embedded in its deal. A single compare-and-swap MongoDB update saves the ledger, audit event and delivered-quantity projection atomically, including on standalone MongoDB without transactions. History records author, time, action, before/after and cancellation reason. Public deal/list responses omit the private ledger; lists also exclude audit history before reading their pages.

No new startup migration is required. Reads do not write. Existing delivered-quantity rows are exposed as legacy shipment records and copied into the ledger on its first successful mutation. Mixed/invalid historical units produce a warning instead of a fabricated remainder. Such rows can be corrected or cancelled. No payment history is inferred from delivered quantities.

Operational limits: 1000 combined payment/shipment records, 5000 audit events, at most 12 MB of embedded ledger data. Reaching a limit returns an error and never truncates history. A deal with an operations ledger containing records cannot be deleted through the normal deal-delete route.

Deploy the backend before the matching frontend and restart the API. Existing unrelated startup migrations still apply. No production database or API restart was performed during development. Real MongoDB tests use disposable `crm_test_*` databases only.
