# Spike 0.3: Masking at runtime and its cost (AD-5)

**Story:** 0.3 · **Date:** 2026-10-31 · **Decision:** **Keep AD-5.** Every rule it makes was needed at runtime, the fresh per-request computation most of all. Four clarifications go into AD-2 and AD-5 (listed under "Architecture text to change").

## Summary

- **Masking works in queries, for parent and child rows.** `frappe.qb.get_query(ignore_permissions=False)` and `frappe.get_list` mask every configured field. That holds for Data, Phone, Email, Int, Date and Currency on Customer, and for `item_name` and `rate` on Sales Order Item rows queried with `parent_doctype="Sales Order"` or as nested child fields. With `ignore_permissions=True`, nothing is masked.
- **Placeholders are always strings.** Currency and Int come back as `'XXXXXXXX'` and Date as `'XX-XX-XXXX'`, so a typed field would break. AD-5's "masked value becomes `null` plus `MASKED`" is required.
- **A revoked unmask permission stays in effect indefinitely.** Frappe caches each user's masked-field set in Redis with no expiry. A role change, a User save and `frappe.clear_cache(user=...)` all leave it in place. After revocation the user kept seeing real values (`TAX-000001`) until a doctype-level or full cache clear. AD-5's fresh computation gave the right answer at every step.
- **Masking follows the session user, not `get_query(user=)`.** Run as Administrator with `user=` set to the masked user, the query returned every value unmasked.
- **A field above the user's permlevel is silently dropped.** There is no error and no key in the result, so `FORBIDDEN` can't be detected from the result. It has to come from metadata.
- **`get_doc()` is not masked.** `get_doc().as_dict()` returned every real value. This confirms AD-4's rule that loaded documents never leave `adapter/permission.py`.
- **Masking is cheap.** It adds 0.29 ms p50 to a 100-row query and 4.9 ms to a 2,000-row query. The fresh masked-set computation costs 0.05 ms.

## Environment

| | |
|---|---|
| Frappe / ERPNext | v16.53.0 / v16.52.1 |
| MariaDB / Redis / Python | 11.8.9 / 7.4.12 / 3.14.10 |
| Hardware | GitHub Codespace, Intel Xeon Platinum 8370C @ 2.80 GHz, 2 cores, 7.8 GB RAM |
| Site | `spike.localhost` (Spikes 0.1 and 0.2), with the masking fixtures added |
| Run | 2026-10-31, about 21:45 UTC; the whole harness runs in about 5 s |
| Evidence | `spikes/results/masking-0-3.json` (raw values and types) and `masking-0-3.md` (tables) |

## Method

**Fixtures** (`spikes/fixtures.py`, `ensure_masking`), all configured through Frappe's own settings:
- Masked custom fields on Customer, one per fieldtype: `spike_credit` (Currency), `spike_since` (Date), `spike_score` (Int), `spike_phone` (Data, Phone) and `spike_email` (Data, Email). Plus an unmasked control (`spike_note`) and a permlevel-1 field (`spike_secret`).
- Standard fields masked by Property Setter: Customer `tax_id`, and Sales Order Item `item_name` and `rate`.
- Role `Spike Unmask`: read plus `mask` (permission to see unmasked values) at level 0 on Customer and Sales Order, through Custom DocPerm.
- User `spike.masked@example.com` with Stock User, which reads level 0 only on Customer and Sales Order. (Sales User can read Customer level 1, so it can't test the permlevel case.)
- 2,000 Customers carrying values in every masked field.

**Harness** (`spikes/masking_check.py`) runs each matrix row as that user and records the raw value and Python type Frappe returns. Each step of the role-change scenario starts a fresh Frappe request context. The scenario reads Frappe's cached masked set (`meta.get_masked_fields()`), AD-5's fresh computation (`meta.get_permlevel_access("mask", user=)` over the masked fields), the Redis key and its TTL, and what a query returns.

**Timing:** the same query as the same user, with masking on and with `Meta.get_masked_fields` patched to return nothing, 30 trials each, warm. The masked-set lookups ran 300 times each.

## Results

### Parent fields, as the masked user

| Field | Raw value | `get_query` (dict and list) | `get_list` | `get_doc().as_dict()` |
|---|---|---|---|---|
| `tax_id` (Data) | `'TAX-000001'` | `'XXXXXXXX'` | `'XXXXXXXX'` | `'TAX-000001'` |
| `spike_credit` (Currency) | `26729.4` (float) | `'XXXXXXXX'` (str) | `'XXXXXXXX'` (str) | `26729.4` |
| `spike_since` (Date) | `2020-01-02` (date) | `'XX-XX-XXXX'` (str) | `'XX-XX-XXXX'` (str) | `2020-01-02` |
| `spike_score` (Int) | `232` (int) | `'XXXXXXXX'` (str) | `'XXXXXXXX'` (str) | `232` |
| `spike_phone` (Phone) | `'+15550000001'` | `'+15XXXXXX'` | `'+15XXXXXX'` | `'+15550000001'` |
| `spike_email` (Email) | `'buyer0001@example.com'` | `'XXXXXX@example.com'` | `'XXXXXX@example.com'` | `'buyer0001@example.com'` |
| `spike_note` (unmasked) | `'note 1'` | `'note 1'` | `'note 1'` | `'note 1'` |

`pluck` on `spike_credit` also returns `'XXXXXXXX'`. The phone and email placeholders keep part of the real value: the first 3 characters and the domain.

### Child rows (Sales Order Item, `item_name` and `rate` masked)

| Query | Result |
|---|---|
| `get_query("Sales Order Item", parent_doctype="Sales Order")` | `item_name` and `rate` are `'XXXXXXXX'`; `qty` is real |
| The same, without `parent_doctype` | `PermissionError`: "Insufficient Permission for Sales Order Item" |
| `get_query("Sales Order", fields=["name", {"items": [...]}])` | Nested rows are masked the same way |
| `ignore_permissions=True` | Real values: `'Spike Item 050'`, `58.41` |

### Unmask role granted and revoked without clearing caches

Each step is a new request as the masked user. Role changes go through `User.add_roles` and `remove_roles`, which save the User.

| Step | Role held | Redis key present | Key TTL (s) | `get_masked_fields` | Fresh computation | Query `tax_id` |
|---|---|---|---|---|---|---|
| start: no unmask role, caches cleared | False | False | -2 | 6 fields | 6 fields | `XXXXXXXX` |
| unmask role granted, no cache clear | True | True | -1 | 6 fields | 0 fields | `XXXXXXXX` |
| unmask role revoked, no cache clear | False | True | -1 | 6 fields | 6 fields | `XXXXXXXX` |
| after `frappe.clear_cache(user=...)` | False | True | -1 | 6 fields | 6 fields | `XXXXXXXX` |
| after `frappe.clear_cache()` | False | False | -2 | 6 fields | 6 fields | `XXXXXXXX` |
| granted, caches cleared, cache warmed | True | False | -2 | 0 fields | 0 fields | `TAX-000001` |
| then revoked, no cache clear | False | True | -1 | 0 fields | 6 fields | **`TAX-000001`** |
| still revoked, next request | False | True | -1 | 0 fields | 6 fields | **`TAX-000001`** |
| revoked, after `frappe.clear_cache(user=...)` | False | True | -1 | 0 fields | 6 fields | **`TAX-000001`** |
| revoked, after `frappe.clear_cache(doctype="Customer")` | False | False | -2 | 6 fields | 6 fields | `XXXXXXXX` |
| revoked, after `frappe.clear_cache()` | False | False | -2 | 6 fields | 6 fields | `XXXXXXXX` |

TTL `-1` means the key never expires; `-2` means it's absent. "Redis key present" is read before the step's own lookup, so it shows the state that lookup found.

- **Revoking unmask leaks.** The user keeps seeing real values indefinitely.
- **Granting unmask over-masks.** The user keeps seeing placeholders until a cache clear. That is safe but wrong.

Only `clear_cache(doctype=...)` or a full clear resets the cache.

### Other observations

- **The session user decides masking, not `user=`.** `get_query(..., user="spike.masked@example.com")` run as Administrator returned every value unmasked. `get_masked_fields` reads `frappe.session.user`, and returns nothing for Administrator.
- **Fields above the user's permlevel are silently dropped.** With `spike_secret` (level 1) in `fields`:
  - `get_query` and `get_list` returned rows without that key
  - with only `spike_secret` requested, rows held just `name`
  - no exception was raised

### Timing (warm, ms)

| Measure | p50 | p95 |
|---|---|---|
| 100-row query, masking on / off | 1.24 / 0.95 | 2.22 / 2.04 |
| Masking overhead, 100 rows | 0.29 | 0.19 |
| 2,000-row query, masking on / off | 16.60 / 11.73 | 27.91 / 18.13 |
| Masking overhead, 2,000 rows | 4.87 | 9.78 |
| `get_masked_fields`, cached | 0.006 | 0.009 |
| `get_masked_fields`, cache miss | 0.620 | 0.955 |
| AD-5 fresh masked-set computation | 0.050 | 0.071 |

Queries are over 30 trials and lookups over 300. The p95 overhead is a difference of two p95s, so it can come out smaller than the p50 overhead.

## Decision for AD-5

**Keep AD-5.**

- **The union with a fresh computation is necessary.** Frappe's cached masked set has no expiry and survives role changes and `clear_cache(user=...)`. The fresh computation was right at every step and costs 0.05 ms.
- **Metadata-driven `MASKED`, not placeholder comparison, is necessary.** Placeholders are strings in numeric and date fields, and phone and email placeholders keep part of the real value.
- **`FORBIDDEN` must come from permitted-fields metadata.** Frappe drops above-permlevel fields silently, so the result alone can't tell "unreadable" from "not requested".
- **Masking costs too little to matter** next to AD-4's permission check: 0.3 ms per 100 rows, against about 300–1,900 ms for the page.

### Architecture text to change

These clarify AD-2 and AD-5. They don't change any rule.

1. **AD-2:** `_authorized_query` must run as the session user. Masking reads `frappe.session.user` and ignores `get_query(user=)`, so passing any other user returns unmasked values. Assert `user == frappe.session.user`, and never set the session to another user for a query.
2. **AD-2:** a child-table read must pass `parent_doctype`. Without it Frappe raises `PermissionError`; with it, masking uses the parent's DocPerm `mask` setting.
3. **AD-5:** state why the union is needed: Frappe's per-user masked-field cache (`masked_fields::<doctype>::<parent>::<user>`) has no expiry and is not cleared by role changes or `clear_cache(user=...)` (this spike). Also state the reverse case: a newly granted unmask permission shows `MASKED` until Frappe's cache is cleared, because Frappe already replaced the value. The admin docs should say that granting unmask needs a cache clear for the DocType.
4. **AD-5:** `FORBIDDEN` is decided from the user's permitted fields before the query, because Frappe silently drops above-permlevel fields from results.

## Limitations

- Observed on one site and version pair. Frappe's masking code is recent, and it may change between patch releases.
- Only `get_query`, `get_list` and `get_doc().as_dict()` were checked. Report queries (`desk/query_report.py`) mask separately and are out of DocWeave's scope.
- Timing ran warm and in process, on a 2-core Codespace.

## Rerun

1. Spikes 0.1 and 0.2 setup: `bash spikes/setup_site.sh`.
2. `cd ~/frappe-bench/sites && ../env/bin/python /workspaces/docweave/spikes/fixtures.py --site spike.localhost`. This adds the masking setup and skips anything already present.
3. `../env/bin/python /workspaces/docweave/spikes/masking_check.py --site spike.localhost`, about 5 s. It writes `spikes/results/masking-0-3.{json,md}`. It needs no gunicorn and no quiet bench.
