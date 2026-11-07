"""The only reader of DocWeave Settings."""

import frappe

from docweave.core.types import SettingsView


def get_settings() -> SettingsView:
	doc = frappe.get_single("DocWeave Settings")
	return SettingsView(
		enabled=bool(doc.enabled),
		allow_administrator=bool(doc.allow_administrator),
		allowed_roles=frozenset(r.role for r in doc.allowed_roles if r.role),
		exposed_doctypes=tuple(r.document_type for r in doc.exposed_doctypes if r.document_type),
		max_page_size=int(doc.max_page_size),
		scan_budget=int(doc.scan_budget),
		max_depth=int(doc.max_depth),
		child_fanout_estimate=int(doc.child_fanout_estimate),
		max_child_rows=int(doc.max_child_rows),
		modified=str(doc.modified or ""),
	)
