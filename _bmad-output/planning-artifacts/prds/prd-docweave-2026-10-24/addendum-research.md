# DocWeave research digest (2026-10-24)
F = fact from source; I = my inference. Searches were shallow; verify before citing.

## 1. Existing Frappe GraphQL projects
F: No rtCamp frappe-graphql repo found. Main project is leam-tech/frappe_graphql (Python, MIT). https://github.com/leam-tech/frappe_graphql
F: Features: doc get/list, cursor pagination, nested link queries, SocketIO subscriptions, file upload mutation, set_value/save_doc/delete_doc, read-permission checks, hooks for SDL/middleware. Depth limit 10; introspection off in prod by default; sort restricted to indexed/unique fields (+name/creation/modified).
F: Stars ~37-53 (sources differ); last push reported Feb 2023 (ecosyste.ms: https://awesome.ecosyste.ms/projects/709106). No stated v15/v16 support.
F: Forum (Nov 2024 - Oct 2025) says it has bugs, lacks Frappe 15+ compatibility, is a plugin not core, and "looks abandoned". https://discuss.frappe.io/t/why-frappe-framework-needs-graphql-at-its-core/137536
I: Field is effectively empty for v16; no known planner-based/N+1-free or masking-aware option. Calls to confirm: whether it uses per-resolver get_doc (likely N+1), and any other forks.

## 2. REST pain points (community, mixed versions)
F: List endpoints don't return child rows; maintainer reply: child docs "not first class" due to parent-based permissions. https://discuss.frappe.io/t/getting-child-tables-with-rest-api/99518
F: Common workaround = list names then GET /api/resource/X/{name} per doc (N+1); slow, "Broken Pipe" reports. https://discuss.frappe.io/t/api-get-child-tables-with-single-call/100088
F: Backtick child-table fields in `fields` yields duplicated parent rows instead of nested arrays. https://discuss.frappe.io/t/fetch-doctype-list-included-childtable-by-rest-api/83588
F: Over-fetching of full docs, bulk-sync cost, egress costs, REST "not type safe" (same GraphQL thread above).
F: Usual fix is custom whitelisted methods (/api/method).
I: Permission pitfall to design around: child permissions derive from the parent, so batched child loads must apply parent-level checks.

## 3. Frappe v16
F: v16 page https://frappe.io/framework/version-16 ; releases at v16.32.0 (https://newreleases.io/project/github/frappe/frappe/release/v16.32.0).
F: Data masking: per-field `mask` property + `mask` permtype; applied in frappe.db.get_list (DatabaseQuery); Admin unmasked; documented as experimental/nightly at time of docs. https://docs.frappe.io/framework/data-masking
F: No evidence found that direct frappe.qb queries apply masking.
I: A DocWeave planner using qb for batching must apply masking itself (or go through get_list) - key design risk; verify in v16 source.
F: No official GraphQL plan found. Official PR "feat(mcp): add a built-in MCP server (#44431)" in frappe/frappe: /api/v2/mcp, 15 tools, per-site MCP Settings, reuses auth/permissions; merge status unknown. https://discuss.frappe.io/t/mcp-server-for-frappe/147635
F: Community MCP servers: vyogotech/frappe-mcp-server (Go, https://github.com/vyogotech/frappe-mcp-server), frappe-mcp-server on PyPI (REST wrapper), sajmustafake/frappe-dev-mcp-server, Frax (onehash), Frappe Assistant Core, rakeshgangwar/erpnext-mcp-server, Casys 120-tool server (https://discuss.frappe.io/t/mcp-server-for-erpnext-120-tools-to-connect-ai-agents-to-your-erp/161198). Thread notes auth setup difficulty and LLM security worries.
I: Most wrap REST (inherit its N+1/over-fetch); the official MCP tool set is generic CRUD. GraphQL differentiator = typed, batched, field-selective reads for agents. Overlap risk with official MCP: position as complementary/backing layer.

## 4. GraphQL as MCP foundation
F: Apollo MCP Server (GA Oct 2025) maps schema operations to MCP tools; argues introspection + precise field selection give agents machine-readable domain map and lower token cost. https://www.apollographql.com/blog/the-future-of-mcp-is-graphql/ , https://www.apollographql.com/blog/apollo-mcp-server-1-0-is-generally-available
F: Zuplo pattern: two generic MCP tools (introspect, execute query). https://zuplo.com/blog/mcp-server-graphql.md
F: Caveat article: GraphQL as typed layer behind agent tools, not mandatory. https://levelup.gitconnected.com/graphql-and-ai-the-emerging-convergence-reshaping-api-architecture-in-2026-68e2652cbd19
Note: sources are largely vendor-authored.
I: DocWeave can ship a SDL + persisted-operation list so Apollo MCP/generic servers work without custom code; depth/cost limits and masking matter more for agents.
