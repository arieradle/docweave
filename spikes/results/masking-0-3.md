# Masking observations (v16.53.0, ERPNext v16.52.1, 2026-10-31 21:53 UTC)

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

`get_doc` then `apply_fieldlevel_read_permissions()` (what Frappe's document endpoints do):

```json
{
 "ok": true,
 "result": {
  "name": {
   "value": "Spike Mask Customer 0001",
   "type": "str"
  },
  "tax_id": {
   "value": "XXXXXXXX",
   "type": "str"
  },
  "spike_note": {
   "value": "note 1",
   "type": "str"
  },
  "spike_email": {
   "value": "XXXXXX@example.com",
   "type": "str"
  },
  "spike_phone": {
   "value": "+15XXXXXX",
   "type": "str"
  },
  "spike_score": {
   "value": "XXXXXXXX",
   "type": "str"
  },
  "spike_since": {
   "value": "XX-XX-XXXX",
   "type": "str"
  },
  "spike_credit": {
   "value": "XXXXXXXX",
   "type": "str"
  },
  "spike_secret": {
   "value": null,
   "type": "NoneType"
  }
 }
}
```

## Filters, sorting and aggregates on masked fields

```json
{
 "filter_equals_real_tax_id": {
  "ok": true,
  "result": [
   {
    "name": {
     "value": "Spike Mask Customer 0001",
     "type": "str"
    }
   }
  ]
 },
 "filter_credit_gt_49000": {
  "ok": true,
  "result": 40
 },
 "order_by_credit_desc_top3": {
  "ok": true,
  "result": [
   {
    "name": {
     "value": "Spike Mask Customer 1517",
     "type": "str"
    },
    "spike_credit": {
     "value": "XXXXXXXX",
     "type": "str"
    }
   },
   {
    "name": {
     "value": "Spike Mask Customer 0818",
     "type": "str"
    },
    "spike_credit": {
     "value": "XXXXXXXX",
     "type": "str"
    }
   },
   {
    "name": {
     "value": "Spike Mask Customer 1327",
     "type": "str"
    },
    "spike_credit": {
     "value": "XXXXXXXX",
     "type": "str"
    }
   }
  ]
 },
 "sum_credit": {
  "ok": true,
  "result": [
   {
    "total": {
     "value": 49979459.27,
     "type": "float"
    }
   }
  ]
 },
 "max_since": {
  "ok": true,
  "result": [
   {
    "latest": {
     "value": "2024-02-08",
     "type": "date"
    }
   }
  ]
 },
 "get_list_filter_real_tax_id": {
  "ok": true,
  "result": [
   {
    "name": {
     "value": "Spike Mask Customer 0001",
     "type": "str"
    }
   }
  ]
 },
 "filter_on_level1_field": {
  "ok": false,
  "exception": "PermissionError",
  "message": "You do not have permission to access field: <strong>Customer.spike_secret</strong>"
 },
 "real_count_credit_gt_49000": 40
}
```

## Child rows (Sales Order Item, masked `item_name` and `rate`)

```json
{
 "with_parent_doctype": {
  "ok": true,
  "result": [
   {
    "name": {
     "value": "SPK-SO-5-0001-001",
     "type": "str"
    },
    "parent": {
     "value": "SPK-SO-5-0001",
     "type": "str"
    },
    "item_name": {
     "value": "XXXXXXXX",
     "type": "str"
    },
    "rate": {
     "value": "XXXXXXXX",
     "type": "str"
    },
    "qty": {
     "value": 6.0,
     "type": "float"
    }
   },
   {
    "name": {
     "value": "SPK-SO-5-0001-002",
     "type": "str"
    },
    "parent": {
     "value": "SPK-SO-5-0001",
     "type": "str"
    },
    "item_name": {
     "value": "XXXXXXXX",
     "type": "str"
    },
    "rate": {
     "value": "XXXXXXXX",
     "type": "str"
    },
    "qty": {
     "value": 19.0,
     "type": "float"
    }
   }
  ]
 },
 "without_parent_doctype": {
  "ok": false,
  "exception": "PermissionError",
  "message": "Insufficient Permission for <strong>Sales Order Item</strong>"
 },
 "nested_child_fields": {
  "ok": true,
  "result": [
   {
    "name": {
     "value": "SPK-SO-5-0001",
     "type": "str"
    },
    "items": {
     "value": [
      {
       "item_name": {
        "value": "XXXXXXXX",
        "type": "str"
       },
       "rate": {
        "value": "XXXXXXXX",
        "type": "str"
       },
       "qty": {
        "value": 6.0,
        "type": "float"
       }
      },
      {
       "item_name": {
        "value": "XXXXXXXX",
        "type": "str"
       },
       "rate": {
        "value": "XXXXXXXX",
        "type": "str"
       },
       "qty": {
        "value": 19.0,
        "type": "float"
       }
      },
      {
       "item_name": {
        "value": "XXXXXXXX",
        "type": "str"
       },
       "rate": {
        "value": "XXXXXXXX",
        "type": "str"
       },
       "qty": {
        "value": 19.0,
        "type": "float"
       }
      },
      {
       "item_name": {
        "value": "XXXXXXXX",
        "type": "str"
       },
       "rate": {
        "value": "XXXXXXXX",
        "type": "str"
       },
       "qty": {
        "value": 3.0,
        "type": "float"
       }
      },
      {
       "item_name": {
        "value": "XXXXXXXX",
        "type": "str"
       },
       "rate": {
        "value": "XXXXXXXX",
        "type": "str"
       },
       "qty": {
        "value": 6.0,
        "type": "float"
       }
      }
     ],
     "type": "list"
    }
   }
  ]
 },
 "cached_masked_child": [
  "item_name",
  "rate"
 ],
 "fresh_masked_child": [
  "item_name",
  "rate"
 ],
 "cached_masked_child_no_parent": [
  "item_name",
  "rate"
 ]
}
```

## `ignore_permissions=True`

```json
{
 "parent": {
  "ok": true,
  "result": [
   {
    "name": {
     "value": "Spike Mask Customer 0001",
     "type": "str"
    },
    "tax_id": {
     "value": "TAX-000001",
     "type": "str"
    },
    "spike_credit": {
     "value": 26729.4,
     "type": "float"
    },
    "spike_since": {
     "value": "2020-01-02",
     "type": "date"
    },
    "spike_score": {
     "value": 232,
     "type": "int"
    },
    "spike_phone": {
     "value": "+15550000001",
     "type": "str"
    },
    "spike_email": {
     "value": "buyer0001@example.com",
     "type": "str"
    },
    "spike_note": {
     "value": "note 1",
     "type": "str"
    }
   }
  ]
 },
 "child": {
  "ok": true,
  "result": [
   {
    "name": {
     "value": "SPK-SO-5-0001-001",
     "type": "str"
    },
    "parent": {
     "value": "SPK-SO-5-0001",
     "type": "str"
    },
    "item_name": {
     "value": "Spike Item 050",
     "type": "str"
    },
    "rate": {
     "value": 58.41,
     "type": "float"
    },
    "qty": {
     "value": 6.0,
     "type": "float"
    }
   },
   {
    "name": {
     "value": "SPK-SO-5-0001-002",
     "type": "str"
    },
    "parent": {
     "value": "SPK-SO-5-0001",
     "type": "str"
    },
    "item_name": {
     "value": "Spike Item 049",
     "type": "str"
    },
    "rate": {
     "value": 436.95,
     "type": "float"
    },
    "qty": {
     "value": 19.0,
     "type": "float"
    }
   }
  ]
 }
}
```

## Session user and `get_query(user=)`

```json
{
 "session=Administrator user=spike.masked@example.com": {
  "ok": true,
  "result": [
   {
    "name": {
     "value": "Spike Mask Customer 0001",
     "type": "str"
    },
    "tax_id": {
     "value": "TAX-000001",
     "type": "str"
    }
   }
  ]
 },
 "session=spike.unmasked@example.com user=spike.masked@example.com": {
  "ok": true,
  "result": [
   {
    "name": {
     "value": "Spike Mask Customer 0001",
     "type": "str"
    },
    "tax_id": {
     "value": "TAX-000001",
     "type": "str"
    }
   }
  ]
 },
 "session=spike.masked@example.com user=spike.unmasked@example.com": {
  "ok": true,
  "result": [
   {
    "name": {
     "value": "Spike Mask Customer 0001",
     "type": "str"
    },
    "tax_id": {
     "value": "XXXXXXXX",
     "type": "str"
    }
   }
  ]
 },
 "fresh_masked for Administrator": [],
 "get_masked_fields for Administrator": []
}
```

## Unmask role granted and revoked without clearing caches

| Step | Role held | Redis key present | Key TTL (s) | `get_masked_fields` | Fresh computation | Query `tax_id` | Child cached / fresh | Child query `rate` |
|---|---|---|---|---|---|---|---|---|
| start: no unmask role, caches cleared | False | False | -2 | 6 fields | 6 fields | `XXXXXXXX` | 2 / 2 | `XXXXXXXX` |
| unmask role granted, no cache clear | True | True | -1 | 6 fields | 0 fields | `XXXXXXXX` | 2 / 0 | `XXXXXXXX` |
| unmask role revoked, no cache clear | False | True | -1 | 6 fields | 6 fields | `XXXXXXXX` | 2 / 2 | `XXXXXXXX` |
| after frappe.clear_cache(user=...) | False | True | -1 | 6 fields | 6 fields | `XXXXXXXX` | 2 / 2 | `XXXXXXXX` |
| after frappe.clear_cache() | False | False | -2 | 6 fields | 6 fields | `XXXXXXXX` | 2 / 2 | `XXXXXXXX` |
| granted, caches cleared, cache warmed | True | False | -2 | 0 fields | 0 fields | `TAX-000001` | 0 / 0 | `58.41` |
| then revoked, no cache clear | False | True | -1 | 0 fields | 6 fields | `TAX-000001` | 0 / 2 | `58.41` |
| still revoked, next request | False | True | -1 | 0 fields | 6 fields | `TAX-000001` | 0 / 2 | `58.41` |
| revoked, after frappe.clear_cache(user=...) | False | True | -1 | 0 fields | 6 fields | `TAX-000001` | 0 / 2 | `58.41` |
| revoked, after frappe.clear_cache(doctype='Sales Order') | False | True | -1 | 0 fields | 6 fields | `TAX-000001` | 2 / 2 | `XXXXXXXX` |
| revoked, after frappe.clear_cache(doctype='Customer') | False | False | -2 | 6 fields | 6 fields | `XXXXXXXX` | 2 / 2 | `XXXXXXXX` |
| revoked, after frappe.clear_cache() | False | False | -2 | 6 fields | 6 fields | `XXXXXXXX` | 2 / 2 | `XXXXXXXX` |

## Field above the user's permlevel

```json
{
 "query_with_level1_field": {
  "ok": true,
  "result": [
   {
    "name": {
     "value": "Spike Mask Customer 0001",
     "type": "str"
    },
    "spike_note": {
     "value": "note 1",
     "type": "str"
    }
   }
  ]
 },
 "only_level1_field": {
  "ok": true,
  "result": [
   {
    "name": {
     "value": "Spike Mask Customer 0001",
     "type": "str"
    }
   }
  ]
 },
 "get_list_with_level1_field": {
  "ok": true,
  "result": [
   {
    "name": {
     "value": "Spike Mask Customer 0001",
     "type": "str"
    },
    "spike_note": {
     "value": "note 1",
     "type": "str"
    }
   }
  ]
 }
}
```


## Timing (ms; 30 trials per query, 300 per in-request lookup, 30 per first call)

| Measure | p50 | p95 | Paired overhead p50 | Paired overhead p95 | Overhead % (p50) |
|---|---|---|---|---|---|
| Query 100 rows, masking on | 1.19 | 1.88 | 0.27 | 0.63 | 29% |
| Query 100 rows, masking patched off | 0.92 | 1.26 | | | |
| Query 200 rows, masking on | 1.76 | 2.97 | 0.47 | 1.42 | 37% |
| Query 200 rows, masking patched off | 1.28 | 1.86 | | | |
| Query 2000 rows, masking on | 17.01 | 43.55 | 5.29 | 17.26 | 42% |
| Query 2000 rows, masking patched off | 11.94 | 22.89 | | | |
| get_masked_fields_cached | 0.005 | 0.007 | | | |
| get_masked_fields_cache_miss | 1.049 | 2.263 | | | |
| get_masked_fields_first_call_of_request | 0.228 | 0.372 | | | |
| fresh_masked_set | 0.044 | 0.062 | | | |
| fresh_masked_set_first_call_of_request | 0.152 | 0.217 | | | |
