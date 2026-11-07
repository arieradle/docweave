import frappe
from frappe.model.document import Document

SETTINGS_NAME = "DocWeave Settings"
LIMIT_FIELDS = (
	"max_page_size",
	"scan_budget",
	"max_depth",
	"child_fanout_estimate",
	"max_child_rows",
)


class DocWeaveSettings(Document):
	def validate(self):
		self._validate_exposed_doctypes()
		self._validate_limits()

	def _validate_exposed_doctypes(self):
		seen = set()
		for row in self.exposed_doctypes:
			name = row.document_type
			if not name:
				continue  # the required-field check reports it
			if name in seen:
				frappe.throw(f"{name} is listed more than once in Exposed DocTypes (row {row.idx}).")
			seen.add(name)
			if name == SETTINGS_NAME:
				frappe.throw(f"{name} cannot be exposed: the settings are never part of the API.")
			try:
				meta = frappe.get_meta(name)
			except Exception:  # get_meta raises DoesNotExistError for an unknown DocType
				frappe.throw(f"{name} cannot be exposed: no such DocType.")
			if meta.istable:
				frappe.throw(
					f"{name} cannot be exposed: it is a child table and is reached through its parent."
				)
			if meta.issingle:
				frappe.throw(f"{name} cannot be exposed: it is a Single DocType.")

	def _validate_limits(self):
		for fieldname in LIMIT_FIELDS:
			if (self.get(fieldname) or 0) < 1:
				label = self.meta.get_label(fieldname)
				frappe.throw(f"{label} must be at least 1.")
