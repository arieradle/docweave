# Masking observations (v16.53.0, ERPNext v16.52.1, 2026-10-31 21:45 UTC)

## Parent fields, as the masked user

| Field | Raw value | `get_query` as_dict | `get_query` as_list | `get_list` | `get_doc().as_dict()` |
|---|---|---|---|---|---|
| name | `'Spike Mask Customer 0001'` (str) | `'Spike Mask Customer 0001'` (str) | `'Spike Mask Customer 0001'` (str) | `'Spike Mask Customer 0001'` (str) | `'Spike Mask Customer 0001'` (str) |
| tax_id | `'TAX-000001'` (str) | `'XXXXXXXX'` (str) | `'XXXXXXXX'` (str) | `'XXXXXXXX'` (str) | `'TAX-000001'` (str) |
| spike_credit | `26729.4` (float) | `'XXXXXXXX'` (str) | `'XXXXXXXX'` (str) | `'XXXXXXXX'` (str) | `26729.4` (float) |
| spike_since | `'2020-01-02'` (date) | `'XX-XX-XXXX'` (str) | `'XX-XX-XXXX'` (str) | `'XX-XX-XXXX'` (str) | `'2020-01-02'` (date) |
| spike_score | `232` (int) | `'XXXXXXXX'` (str) | `'XXXXXXXX'` (str) | `'XXXXXXXX'` (str) | `232` (int) |
| spike_phone | `'+15550000001'` (str) | `'+15XXXXXX'` (str) | `'+15XXXXXX'` (str) | `'+15XXXXXX'` (str) | `'+15550000001'` (str) |
| spike_email | `'buyer0001@example.com'` (str) | `'XXXXXX@example.com'` (str) | `'XXXXXX@example.com'` (str) | `'XXXXXX@example.com'` (str) | `'buyer0001@example.com'` (str) |
| spike_note | `'note 1'` (str) | `'note 1'` (str) | `'note 1'` (str) | `'note 1'` (str) | `'note 1'` (str) |

`pluck` on `spike_credit`: {"ok": true, "result": [{"value": "XXXXXXXX", "type": "str"}]}

## Child rows (Sales Order Item, masked `item_name` and `rate`)

- **with_parent_doctype**: `{"ok": true, "result": [{"name": {"value": "SPK-SO-5-0001-001", "type": "str"}, "parent": {"value": "SPK-SO-5-0001", "type": "str"}, "item_name": {"value": "XXXXXXXX", "type": "str"}, "rate": {"value": "XXXXXXXX", "type": "str"}, "qty": {"value": 6.0, "type": "float"}}, {"name": {"value": "SPK-SO-5-0001-002", "type": "str"}, "parent": {"value": "SPK-SO-5-0001", "type": "str"}, "item_name": {"value": "XXXXXXXX", "type": "str"}, "rate": {"value": "XXXXXXXX", "type": "str"}, "qty": {"value": 19.0, "type": "float"}}]}`
- **without_parent_doctype**: `{"ok": false, "exception": "PermissionError", "message": "Insufficient Permission for <strong>Sales Order Item</strong>"}`
- **nested_child_fields**: `{"ok": true, "result": [{"name": {"value": "SPK-SO-5-0001", "type": "str"}, "items": {"value": "[{'item_name': 'XXXXXXXX', 'rate': 'XXXXXXXX', 'qty': 6.0}, {'item_name': 'XXXXXXXX', 'rate': 'XXXXXXXX', 'qty': 19.0}, {'item_name': 'XXXXXXXX', 'rate': 'XXXXXXXX', 'qty': 19.0}, {'item_name': 'XXXXXXXX', 'rate': 'XXXXXXXX', 'qty': 3.0}, {'item_name': 'XXXXXXXX', 'rate': 'XXXXXXXX', 'qty': 6.0}]", "type": "list"}}]}`
- cached masked set with parent: `['item_name', 'rate']`, without parent: `['item_name', 'rate']`

## `ignore_permissions=True`

`{"parent": {"ok": true, "result": [{"name": {"value": "Spike Mask Customer 0001", "type": "str"}, "tax_id": {"value": "TAX-000001", "type": "str"}, "spike_credit": {"value": 26729.4, "type": "float"}, "spike_since": {"value": "2020-01-02", "type": "date"}, "spike_score": {"value": 232, "type": "int"}, "spike_phone": {"value": "+15550000001", "type": "str"}, "spike_email": {"value": "buyer0001@example.com", "type": "str"}, "spike_note": {"value": "note 1", "type": "str"}}]}, "child": {"ok": true, "result": [{"name": {"value": "SPK-SO-5-0001-001", "type": "str"}, "parent": {"value": "SPK-SO-5-0001", "type": "str"}, "item_name": {"value": "Spike Item 050", "type": "str"}, "rate": {"value": 58.41, "type": "float"}, "qty": {"value": 6.0, "type": "float"}}, {"name": {"value": "SPK-SO-5-0001-002", "type": "str"}, "parent": {"value": "SPK-SO-5-0001", "type": "str"}, "item_name": {"value": "Spike`

## Session user differs from `user=`

`{"ok": true, "result": [{"name": {"value": "Spike Mask Customer 0001", "type": "str"}, "tax_id": {"value": "TAX-000001", "type": "str"}, "spike_credit": {"value": 26729.4, "type": "float"}, "spike_since": {"value": "2020-01-02", "type": "date"}, "spike_score": {"value": 232, "type": "int"}, "spike_phone": {"value": "+15550000001", "type": "str"}, "spike_email": {"value": "buyer0001@example.com", "type": "str"}, "spike_note": {"value": "note 1", "type": "str"}}]}`

## Unmask role granted and revoked without clearing caches

| Step | Role held | Redis key present | Key TTL (s) | `get_masked_fields` | Fresh computation | Query `tax_id` |
|---|---|---|---|---|---|---|
| start: no unmask role, caches cleared | False | False | -2 | 6 fields | 6 fields | `XXXXXXXX` |
| unmask role granted, no cache clear | True | True | -1 | 6 fields | 0 fields | `XXXXXXXX` |
| unmask role revoked, no cache clear | False | True | -1 | 6 fields | 6 fields | `XXXXXXXX` |
| after frappe.clear_cache(user=...) | False | True | -1 | 6 fields | 6 fields | `XXXXXXXX` |
| after frappe.clear_cache() | False | False | -2 | 6 fields | 6 fields | `XXXXXXXX` |
| granted, caches cleared, cache warmed | True | False | -2 | 0 fields | 0 fields | `TAX-000001` |
| then revoked, no cache clear | False | True | -1 | 0 fields | 6 fields | `TAX-000001` |
| still revoked, next request | False | True | -1 | 0 fields | 6 fields | `TAX-000001` |
| revoked, after frappe.clear_cache(user=...) | False | True | -1 | 0 fields | 6 fields | `TAX-000001` |
| revoked, after frappe.clear_cache(doctype='Customer') | False | False | -2 | 6 fields | 6 fields | `XXXXXXXX` |
| revoked, after frappe.clear_cache() | False | False | -2 | 6 fields | 6 fields | `XXXXXXXX` |

## Field above the user's permlevel

- **query_with_level1_field**: `{"ok": true, "result": [{"name": {"value": "Spike Mask Customer 0001", "type": "str"}, "spike_note": {"value": "note 1", "type": "str"}}]}`
- **only_level1_field**: `{"ok": true, "result": [{"name": {"value": "Spike Mask Customer 0001", "type": "str"}}]}`
- **get_list_with_level1_field**: `{"ok": true, "result": [{"name": {"value": "Spike Mask Customer 0001", "type": "str"}, "spike_note": {"value": "note 1", "type": "str"}}]}`

## Timing (30 trials per query; 300 per lookup; ms)

| Measure | p50 | p95 | Overhead p50 | Overhead p95 |
|---|---|---|---|---|
| Query 100 rows, masking on | 1.24 | 2.22 | 0.29 | 0.19 |
| Query 100 rows, masking patched off | 0.95 | 2.04 | | |
| Query 2000 rows, masking on | 16.60 | 27.91 | 4.87 | 9.78 |
| Query 2000 rows, masking patched off | 11.73 | 18.13 | | |
| get_masked_fields_cached | 0.006 | 0.009 | | |
| get_masked_fields_cache_miss | 0.620 | 0.955 | | |
| fresh_masked_set | 0.050 | 0.071 | | |
