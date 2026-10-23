# Company Pages and Deal Numbers

## Deployment

Deploy the backend before the matching frontend. Restart the API with startup migrations enabled (`SKIP_STARTUP_MIGRATIONS` must not be `1`). Back up MongoDB before deployment.

The idempotent migration `deal_numbers_company_pages_v1` assigns numbers to all existing deals, including archived deals, in `createdAt`, `_id` order. It installs unique partial indexes on `number` and `numberSequence`, seeds the atomic `counters/deal_number` counter, and adds company/deal list indexes. It does not change existing assigned numbers. Production data was not migrated during development; tests use a disposable local database.

## Company Pagination

`GET /companies/page` requires the existing bearer authentication. The legacy `GET /companies` array endpoint remains unchanged.

Query parameters:

| Parameter | Default / Values |
| --- | --- |
| `page` | 1, positive integer |
| `pageSize` | 15, range 1..100 |
| `search` | Optional literal case-insensitive search, up to 200 characters |
| `role` | `provider` or `customer` |
| `sortBy` | `recent` (newest ObjectId first) or `name` |
| `includeDetails` | `false`; includes active addresses and material prices when true |
| `city`, `district` | Optional exact geography matches |
| `administrativeDistrict` | Existing Moscow district enum |
| `materialId` | Optional material ObjectId |
| `priceUnit` | Optional unit; requires material |
| `maxPrice` | Finite nonnegative ceiling; requires material and unit |
| `priceSort` | `default`, `asc`, `desc`; price sorting requires material and unit |

Response: `{items, total, page, pageSize, totalPages, hasNext, hasPrev}`. All filters and price comparisons are applied before the shared count/page facet. Archived companies/addresses/prices are excluded. Related deal history is not included in paged company results.

Search covers names, INN/KPP (including legacy numeric values), company phones/emails, websites, source, segments, and contact-person fields. Unit aliases normalize tonnes (`т`, `тонна`, `тонн`, `тонны`), cubic metres (`м³`, `м3`, `куб.м`, `куб. м`) and pieces. Prices with different units are never ranked together. Geography is not inferred from coordinates.

## Deal Numbers

Deal responses include read-only `number` (for example `СД-000123`) and `numberSequence` (123). Ordinary creation and lead conversion use the same atomic counter. Retrying creation with the same internal deal ID keeps the assigned number. Archived numbers are not reused; gaps are allowed after failed or competing writes.

`GET /deals?search=СД-000123&includeRelations=true` searches numbers alongside the existing company/material search. `sortBy=numberSequence&sortOrder=asc` sorts numerically. Ownership restrictions still apply before search and pagination. Create/PATCH input cannot assign or replace a number.

## Verification

The opt-in `tests/test_crm_mongo_integration.py` uses real JWT authentication, HTTP routes, calculation rules and MongoDB aggregation/indexes. Set `CRM_TEST_MONGO_URI` to a disposable loopback instance; remote hosts are rejected. Each run creates and drops only a random `crm_test_*` database. The normal suite skips this test when the variable is absent.
