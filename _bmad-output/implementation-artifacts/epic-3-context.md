# Epic 3 Context: Writing data (v2, not in v1)

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

Add mutations so clients can create, update and delete documents of Exposed DocTypes, with Frappe's own write permissions and validation applied, without ever overwriting values hidden from the user, and with all of a request's mutations succeeding or failing together. This is the v2 backlog: v1 is read-only and has no `Mutation` root type, and the architecture records only the agreed v2 design, not a binding one. Submit, cancel, amend and bulk operations come after this epic.

## Stories

- Story 3.1: Create mutations with the input contract
- Story 3.2: Sparse update, including child rows
- Story 3.3: Delete and submitted documents
- Story 3.4: All-or-nothing mutation requests

## Requirements & Constraints

- Mutations apply Frappe's write permissions and validation; a user without write permission gets a permission error.
- Updates change only the fields sent, so masked or unreadable values are never overwritten.
- A request's mutations are all or nothing.
- Unreadable documents stay `NOT_FOUND` (no existence disclosure); `FORBIDDEN` is for fields; validation failures are `VALIDATION` with the exception class and a sanitized message.
- Security and permission tests take priority, with negative tests for each rule.

## Technical Decisions

- **Document API only.** Writes use `frappe.get_doc(...).insert()`, `.save()` and `frappe.delete_doc`, never with ignore flags. These calls live in the adapter; the AD-1 boundary test and its allowlist must be extended deliberately for them.
- **Input types.** Exclude system, read-only, `fetch_from` (unless `fetch_if_empty`), virtual, Password and display fields. The epic also excludes `name` unless autoname is Prompt, and `set_only_once` fields from update input.
- **Request-time checks.** Setting a field above the user's write permlevel, or one masked for them, is `FORBIDDEN`, using the same metadata-driven masked/readable computation as reads.
- **Sparse update and children.** Only sent fields change. Child rows are matched by a verified `name`: rows with `name` are patched (hidden columns kept), rows without are inserted, existing rows left out are deleted. A row `name` belonging to another document or another table field is `FORBIDDEN`.
- **Submitted documents.** Only `allow_on_submit` fields may change; delete is refused.
- **Payload.** `{ name, doc }`, with `doc` re-read through the normal read planner and authorized path. If the user can't read the result, `doc` is `null` with `NOT_FOUND`.
- **Transactions.** The transport owns the transaction and rolls back on any mutation error; mutations run in document order and Frappe commits once. Write code never commits. This replaces v1's unconditional rollback in the endpoint's `finally` for mutation requests.
- Names, error codes and the exception map are the same single sources as in v1 (`schema/naming.py`, `core`, `adapter/errors.py`).

## Cross-Story Dependencies

- Depends on all of Epic 1 (schema builder, naming, masking, authorized read path for re-reads, error map) and on Epic 2 only for shared planner machinery.
- 3.1 defines the input contract that 3.2 and 3.3 extend; 3.4 wraps all three in the transport transaction.
- Requires introducing the `Mutation` root type, which v1 explicitly omits, and revisiting the read-only rollback guarantee in the transport.
