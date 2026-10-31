# Epic 0 Context: De-risking spikes

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

Measure the two riskiest architecture bets on a real Frappe v16 + ERPNext site before Epic 1 builds on them. The first bet is the cost of checking every candidate document with a full load plus Frappe's own permission check. The second is whether field masking behaves at runtime the way the Frappe source suggests. Each spike produces a report with numbers and ends in a keep-or-amend decision for its architecture rule. Spike code is throwaway: it lives outside the app package and never ships.

## Stories

- Story 0.1: Spike: time the per-candidate permission check
- Story 0.2: Re-measure AD-4 with the review fixes from Spike 0.1
- Story 0.3: Spike: verify masking at runtime and time its cost

## Requirements & Constraints

- Target platform is exactly Frappe v16.53.0 with ERPNext v16.52.1 on MariaDB 11.8 with Redis. Results are valid only for the recorded versions.
- DocWeave v1 is read-only. Spikes must not depend on any write path in DocWeave itself (fixture generation writes directly to the spike site).
- Testing priority for the project is permissions, masking, then cursor correctness. Spike fixtures should reflect the restriction types that matter: User Permissions on parent links and on child-row links, DocShare, owner-only (`if_owner`) read, select-only users, and masked fields.
- Pagination later relies on a per-list scan budget (default 2,000 candidates) and a maximum page size (default 100). These are the sizes to measure at.

## Technical Decisions

- **Reads always run with permissions applied.** `frappe.qb.get_query` defaults to `ignore_permissions=True`. DocWeave always passes `ignore_permissions=False`, `ignore_user_permissions=False` and the session user. Masking is applied by Frappe when such a query runs.
- **Document-level checks use full Frappe parity.** For each candidate row, load the document with `frappe.get_doc` and call `frappe.has_permission(doctype, "read", doc=doc, user=user)`. Returned values always come from the masked query row, never the loaded document. A user with `select` but not `read` gets nothing, without a scan. A cheaper "build the document from the row" shortcut was rejected because it misses child-row User Permissions, DocShare and permlevel-hidden fields.
- **Masking is metadata-driven.** The masked set is `meta.get_masked_fields(parenttype=...)` combined with a fresh per-request computation from the user's current roles (via `meta.get_permlevel_access("mask", ...)`), because Frappe caches masked fields per user and may not clear that cache when roles change. Masked values become `null` plus a `MASKED` error in the API, never compared against placeholder strings.
- Frappe v16 masks with type-specific placeholders, for example `XXXXXXXX` by default, `XX-XX-XXXX` for dates, and partial values for phone and email.
- **AD-4 outcome (Spikes 0.1 and 0.2):** the full-parity check stays. The default scan budget is lowered from 2,000 to 200 and applied to the architecture and Stories 1.2 and 2.3.
- **AD-5 outcome (Spike 0.3):** AD-5 is kept. The architecture now records why the fresh-computation union is required, the session-user and `parent_doctype` rules (AD-2), the Administrator special case, and that `FORBIDDEN` comes from metadata. AD-6's filter and sort rule now cites the observed leaks.
- Useful v16 APIs: `IntegrationTestCase.assertQueryCount`, `frappe.has_permission(..., ignore_share_permissions=...)`, `frappe.permissions.has_user_permission`, `frappe.model.utils.mask.mask_field_value`.

## Cross-Story Dependencies

- Both spikes need a running Frappe v16.53.0 + ERPNext v16.52.1 site, which the devcontainer does not yet provide.
- Story 0.1 decides whether the architecture's per-candidate check (AD-4) stands. Story 0.2 measures the scan budget Spike 0.1 proposed, at the p95 target, and confirms or replaces Spike 0.1's amendment. Story 0.3 decides the same for masking (AD-5). Epic 1 stories 1.5, 1.6 and 1.7 build on both decisions.
- The two spikes can share one fixture generator and site.
