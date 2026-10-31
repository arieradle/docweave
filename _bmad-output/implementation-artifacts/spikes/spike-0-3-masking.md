# Spike 0.3: Masking at runtime and its cost (AD-5)

**Story:** 0.3 · **Date:** 2026-10-31 · **Decision:** **Keep AD-5.** Every rule it makes was needed at runtime, the fresh per-request computation most of all. The spike also gives hard evidence for AD-6: Frappe leaks masked values through filters, sorting and aggregates. Five clarifications go into AD-2, AD-5 and AD-6 (listed under "Architecture text to change").

## Summary

- **Masking works for returned values, in parent and child rows.** `frappe.qb.get_query(ignore_permissions=False)` and `frappe.get_list` mask every configured field: Data, Phone, Email, Int, Date and Currency on Customer, and `item_name` and `rate` on Sales Order Item, whether queried with `parent_doctype="Sales Order"` or as nested child fields. Loading a document and calling `apply_fieldlevel_read_permissions()`, as Frappe's document endpoints do, masks it too. With `ignore_permissions=True`, or for a plain `get_doc()`, nothing is masked.
- **Masking does not protect filters, sorting or aggregates.** As the masked user:
  - a filter on the real `tax_id` finds the row
  - `spike_credit > 49000` returns the real count (40)
  - `order_by spike_credit` returns the real order
  - `SUM(spike_credit)` and `MAX(spike_since)` return the real values

  AD-6's rule to reject masked fields in filters and sorting is required, not just defensive.
- **Placeholders are always strings.** Currency and Int come back as `'XXXXXXXX'` and Date as `'XX-XX-XXXX'`. Phone and email placeholders keep part of the real value. AD-5's "masked value becomes `null` plus `MASKED`" is required.
- **A revoked unmask permission stays in effect indefinitely.** Frappe caches each user's masked-field set per DocType in Redis with no expiry. A role change, a User save and `frappe.clear_cache(user=...)` all leave it in place. After revocation the user kept seeing real values in parent and child rows until `clear_cache(doctype=...)` for that DocType, or a full clear. AD-5's fresh computation was right at every step.
- **Masking follows the session user, not `get_query(user=)`.** An unmask-holding session querying with `user=` set to the masked user got real values. The masked session querying with `user=` set to the unmask-holder got placeholders.
- **A field above the user's permlevel is silently dropped from results.** There is no error and no key. Filtering on such a field raises `PermissionError`.
- **Masking is cheap in absolute terms.** It adds 29–42% to a plain query, but that's 0.27 ms for 100 rows, 0.47 ms for 200 and 5.3 ms for 2,000. The fresh masked-set computation costs 0.15 ms on a request's first call.

## Environment

| | |
|---|---|
| Frappe / ERPNext | v16.53.0 / v16.52.1 |
| MariaDB / Redis / Python | 11.8.9 / 7.4.12 / 3.14.10 |
| Hardware | GitHub Codespace, Intel Xeon Platinum 8370C @ 2.80 GHz, 2 cores, 7.8 GB RAM |
| Site | `spike.localhost` (Spikes 0.1 and 0.2), with the masking fixtures added |
| Run | 2026-10-31 21:53 UTC; the whole harness runs in about 5 s |
| Evidence | `spikes/results/masking-0-3.json` (raw values, types and environment, all recorded by the harness) and `masking-0-3.md` |

## Method

**Fixtures** (`spikes/fixtures.py`, `ensure_masking`), all configured through Frappe's own settings:
- Masked custom fields on Customer, one per fieldtype: `spike_credit` (Currency), `spike_since` (Date), `spike_score` (Int), `spike_phone` (Data, Phone) and `spike_email` (Data, Email). Plus an unmasked control (`spike_note`) and a permlevel-1 field (`spike_secret`).
- Standard fields masked by Property Setter: Customer `tax_id`, and Sales Order Item `item_name` and `rate`.
- Role `Spike Unmask`: read plus `mask` (permission to see unmasked values) at level 0 on Customer and Sales Order, through Custom DocPerm.
- Two users:
  - `spike.masked@example.com` (Stock User), which reads level 0 only on Customer and Sales Order. Sales User can read Customer level 1, so it can't test the permlevel case.
  - `spike.unmasked@example.com` (Stock User plus the unmask role).
- 2,000 Customers carrying values in every masked field.

**This changes the shared spike site.** Customer's and Sales Order's permissions become Custom DocPerm, and three standard fields are masked for every role without the unmask role. Spikes 0.1 and 0.2 ran before it. A rerun of them on this site measures a different configuration.

**Harness** (`spikes/masking_check.py`) runs each matrix row and records the raw value and Python type Frappe returns. Each step of the role-change scenario starts a fresh Frappe request context. It reads, for Customer and for Sales Order Item under Sales Order:
- Frappe's cached masked set (`meta.get_masked_fields()`)
- AD-5's fresh computation (`meta.get_permlevel_access("mask", user=)` over the masked fields)
- the Redis key and its TTL
- what a query returns

**Timing:** the same query as the same user, with masking on and with `Meta.get_masked_fields` patched to return nothing, interleaved over 30 trials, warm. The harness asserts that the on-run is masked and the off-run is not. Overhead is the per-trial paired difference. The masked-set lookups ran 300 times within a request, plus 30 times as the first call of a new request.

## Results

### Parent fields, as the masked user

| Field | Raw value | `get_query` (dict and list) | `get_list` | Plain `get_doc().as_dict()` | `get_doc` + `apply_fieldlevel_read_permissions()` |
|---|---|---|---|---|---|
| `tax_id` (Data) | `'TAX-000001'` | `'XXXXXXXX'` | `'XXXXXXXX'` | `'TAX-000001'` | `'XXXXXXXX'` |
| `spike_credit` (Currency) | `26729.4` (float) | `'XXXXXXXX'` (str) | `'XXXXXXXX'` (str) | `26729.4` | `'XXXXXXXX'` |
| `spike_since` (Date) | `2020-01-02` (date) | `'XX-XX-XXXX'` (str) | `'XX-XX-XXXX'` (str) | `2020-01-02` | `'XX-XX-XXXX'` |
| `spike_score` (Int) | `232` (int) | `'XXXXXXXX'` (str) | `'XXXXXXXX'` (str) | `232` | `'XXXXXXXX'` |
| `spike_phone` (Phone) | `'+15550000001'` | `'+15XXXXXX'` | `'+15XXXXXX'` | `'+15550000001'` | `'+15XXXXXX'` |
| `spike_email` (Email) | `'buyer0001@example.com'` | `'XXXXXX@example.com'` | `'XXXXXX@example.com'` | `'buyer0001@example.com'` | `'XXXXXX@example.com'` |
| `spike_note` (unmasked) | `'note 1'` | `'note 1'` | `'note 1'` | `'note 1'` | `'note 1'` |
| `spike_secret` (level 1) | `'secret 1'` | dropped (no key) | dropped | — | `None` |

`pluck` on `spike_credit` also returns `'XXXXXXXX'`.

### Filters, sorting and aggregates on masked fields, as the masked user

| Query | Result | Leaks? |
|---|---|---|
| `filters={"tax_id": "TAX-000001"}` (`get_query` and `get_list`) | returns Customer 0001 | yes: confirms the hidden value |
| `filters={"spike_credit": [">", 49000]}` over 2,000 | 40 rows; the true count is 40 | yes: range probing works |
| `order_by="spike_credit desc", limit=3` | Customers 1517, 0818, 1327, values masked | yes: real order |
| `fields=[{"SUM": "spike_credit"}]` | `49979459.27` (float) | yes: real total |
| `fields=[{"MAX": "spike_since"}]` | `2024-02-08` (date) | yes: real value |
| `filters={"spike_secret": "secret 1"}` (level 1) | `PermissionError` | no |

### Child rows (Sales Order Item, `item_name` and `rate` masked)

| Query | Result |
|---|---|
| `get_query("Sales Order Item", parent_doctype="Sales Order")` | `item_name` and `rate` are `'XXXXXXXX'` (str); `qty` is real (float) |
| The same, without `parent_doctype` | `PermissionError`: "Insufficient Permission for Sales Order Item" |
| `get_query("Sales Order", fields=["name", {"items": [...]}])` | Nested rows are masked the same way, with the same types |
| `ignore_permissions=True` | Real values: `'Spike Item 050'`, `58.41` |

The cached and fresh masked sets for the child are both `['item_name', 'rate']`. Frappe's cached set is the same with or without a parent DocType, because the masking metadata is on the child's fields.

### Unmask role granted and revoked without clearing caches

Each step is a new request as the masked user. Role changes go through `User.add_roles` and `remove_roles`, which save the User.

| Step | Role held | Key TTL (s) | Cached / fresh, Customer | Query `tax_id` | Cached / fresh, child | Child query `rate` |
|---|---|---|---|---|---|---|
| start: no unmask role, caches cleared | False | -2 | 6 / 6 | `XXXXXXXX` | 2 / 2 | `XXXXXXXX` |
| unmask role granted, no cache clear | True | -1 | 6 / 0 | `XXXXXXXX` | 2 / 0 | `XXXXXXXX` |
| unmask role revoked, no cache clear | False | -1 | 6 / 6 | `XXXXXXXX` | 2 / 2 | `XXXXXXXX` |
| after `frappe.clear_cache(user=...)` | False | -1 | 6 / 6 | `XXXXXXXX` | 2 / 2 | `XXXXXXXX` |
| after `frappe.clear_cache()` | False | -2 | 6 / 6 | `XXXXXXXX` | 2 / 2 | `XXXXXXXX` |
| granted, caches cleared, cache warmed | True | -2 | 0 / 0 | `TAX-000001` | 0 / 0 | `58.41` |
| then revoked, no cache clear | False | -1 | 0 / 6 | **`TAX-000001`** | 0 / 2 | **`58.41`** |
| still revoked, next request | False | -1 | 0 / 6 | **`TAX-000001`** | 0 / 2 | **`58.41`** |
| revoked, after `frappe.clear_cache(user=...)` | False | -1 | 0 / 6 | **`TAX-000001`** | 0 / 2 | **`58.41`** |
| revoked, after `clear_cache(doctype="Sales Order")` | False | -1 | 0 / 6 | **`TAX-000001`** | 2 / 2 | `XXXXXXXX` |
| revoked, after `clear_cache(doctype="Customer")` | False | -2 | 6 / 6 | `XXXXXXXX` | 2 / 2 | `XXXXXXXX` |
| revoked, after `frappe.clear_cache()` | False | -2 | 6 / 6 | `XXXXXXXX` | 2 / 2 | `XXXXXXXX` |

The TTL is for the Customer key: `-1` means it never expires, and `-2` means it's absent. The full table, with the Redis-key column, is in `masking-0-3.md`.

- **Revoking unmask leaks.** The user keeps seeing real values, in parent and child rows, until that DocType's cache is cleared. Each DocType is reset separately: clearing Sales Order fixed the child rows, but Customer stayed leaked.
- **Granting unmask over-masks.** The user keeps seeing placeholders until a cache clear. That is safe but wrong.

### Session user and `get_query(user=)`

| Session user | `user=` | `tax_id` returned |
|---|---|---|
| Administrator | masked user | `'TAX-000001'` (real) |
| Unmask-holder | masked user | `'TAX-000001'` (real) |
| Masked user | unmask-holder | `'XXXXXXXX'` (masked) |

The fresh computation for Administrator returned no masked fields, the same as Frappe's cached set. That is because Administrator holds every role, including the unmask role. Frappe also special-cases Administrator in `get_masked_fields`. The fresh computation does not, so it would mask Administrator's values at any level where no role has `mask`.

### Timing (warm, ms)

| Measure | p50 | p95 |
|---|---|---|
| 100-row query, masking on / off | 1.19 / 0.92 | 1.88 / 1.26 |
| Masking overhead, 100 rows (paired) | 0.27 (29%) | 0.63 |
| 200-row query, masking on / off | 1.76 / 1.28 | 2.97 / 1.86 |
| Masking overhead, 200 rows (paired) | 0.47 (37%) | 1.42 |
| 2,000-row query, masking on / off | 17.01 / 11.94 | 43.55 / 22.89 |
| Masking overhead, 2,000 rows (paired) | 5.29 (42%) | 17.26 |
| `get_masked_fields`, within a request / first call of a request / Redis miss | 0.005 / 0.228 / 1.049 | 0.007 / 0.372 / 2.263 |
| AD-5 fresh computation, within a request / first call of a request | 0.044 / 0.152 | 0.062 / 0.217 |

Queries ran 30 trials each. In-request lookups ran 300 and first calls 30. With 30 trials, a p95 is roughly the second-slowest run.

## Decision for AD-5

**Keep AD-5.**

- **The union with a fresh computation is necessary.** Frappe's cached masked set has no expiry, and survives role changes and `clear_cache(user=...)`, for parent and child DocTypes. The fresh computation was right at every step and costs about 0.15 ms per request.
- **Metadata-driven `MASKED`, not placeholder comparison, is necessary.** Placeholders are strings in numeric and date fields, and phone and email placeholders keep part of the real value.
- **`FORBIDDEN` must come from permitted-fields metadata.** Frappe drops above-permlevel fields silently, so the result alone can't tell "unreadable" from "not requested".
- **Masking costs too little to matter** next to AD-4's permission check: 0.47 ms for a 200-row page, against about 300–1,900 ms for the page.

### Architecture text to change

These clarify AD-2, AD-5 and AD-6. They don't change any rule.

1. **AD-6:** cite this spike as evidence. Frappe applies filters, `order_by` and aggregates to the real values of masked fields: an equality filter confirms a value, range filters count real values, sorting follows real values, and `SUM`/`MAX` return them. Rejecting masked fields in `FilterIR` and `OrderSpec` is therefore required. Any later aggregate or group-by feature must follow the same rule.
2. **AD-2:** `_authorized_query` must run as the session user. Masking reads `frappe.session.user` and ignores `get_query(user=)`, so passing any other user returns the session user's view. Assert `user == frappe.session.user`, and never set the session to another user for a query. Child-table reads must pass `parent_doctype`. Without it Frappe raises `PermissionError`.
3. **AD-5:** state why the union is needed. Frappe's per-user masked-field cache (`masked_fields::<doctype>::<parent>::<user>`) has no expiry and is not cleared by role changes or `clear_cache(user=...)`. Also state the reverse case: a newly granted unmask permission shows `MASKED` until Frappe's cache is cleared, because Frappe already replaced the value.
4. **AD-5:** special-case Administrator in the fresh computation the way Frappe does (no masking), so the union doesn't mask Administrator's values when `allow_administrator` is on.
5. **AD-5:** `FORBIDDEN` is decided from the user's permitted fields before the query, because Frappe silently drops above-permlevel fields from results.

### For admins (docs, and outside DocWeave)

- **After revoking** an unmask permission, run `bench --site <site> clear-cache`, or `frappe.clear_cache(doctype=...)` for every affected parent and child DocType. Until then Frappe's own list views, `get_list` and REST keep showing that user real values. DocWeave's fresh computation protects only DocWeave.
- **After granting** an unmask permission, do the same, or the user keeps seeing placeholders.
- **Upstream:** the missing expiry and invalidation is worth reporting to Frappe. A role change should invalidate `masked_fields::*::<user>`.

## Limitations

- Observed on one site and version pair. Frappe's masking code is recent and may change between patch releases.
- **Fieldtypes:** only Data, Phone, Email, Int, Date and Currency were tested. Link, Select, Check, Float, Datetime, text fields, Dynamic Link and `fetch_from` fields were not. In particular, whether a masked Link leaks through joins or `fetch_from` is untested. AD-6's derived-load rule assumes it can.
- **Role-change routes:** only `User.add_roles` and `remove_roles` were tested. Those save the User, which also clears the roles cache the fresh computation reads. Role Profile changes, Has Role edits that don't save the User, DocPerm edits that remove `mask`, and Property Setters that toggle `mask` were not tested. If any of these leaves `frappe.get_roles` or the cached meta stale, the fresh computation is stale too.
- Only `get_query`, `get_list` and document loading were checked. Report queries (`desk/query_report.py`) mask separately and are out of DocWeave's scope.
- Timing ran warm and in process on a 2-core Codespace, over small samples (30 trials per query).

## Rerun

1. Spikes 0.1 and 0.2 setup: `bash spikes/setup_site.sh`.
2. `cd ~/frappe-bench/sites && ../env/bin/python /workspaces/docweave/spikes/fixtures.py --site spike.localhost`. This adds the masking setup and skips anything already present.
3. `../env/bin/python /workspaces/docweave/spikes/masking_check.py --site spike.localhost`, about 5 s. It writes `spikes/results/masking-0-3.{json,md}`. It needs no gunicorn and no quiet bench. Run it from `~/frappe-bench/sites`: it uses the current directory as the sites path.
