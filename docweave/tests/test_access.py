import json

import frappe
from frappe.tests import IntegrationTestCase
from frappe.tests.test_api import FrappeAPITestCase, make_request

from docweave import api
from docweave.tests.utils import auth_headers, make_user, set_settings

URL = "/api/method/docweave.api.graphql"
BODY = {"query": "{ __typename }"}
ROLE = "Sales User"


class TestSettingsDoctype(IntegrationTestCase):
	def test_defaults_and_flags(self):
		meta = frappe.get_meta("DocWeave Settings")
		self.assertTrue(meta.issingle)
		self.assertTrue(meta.track_changes)
		self.assertEqual([(p.role, p.read, p.write) for p in meta.permissions], [("System Manager", 1, 1)])
		doc = frappe.new_doc("DocWeave Settings")
		self.assertEqual((doc.enabled, doc.allow_administrator), (0, 0))
		self.assertEqual(
			[
				doc.max_page_size,
				doc.scan_budget,
				doc.max_depth,
				doc.child_fanout_estimate,
				doc.max_child_rows,
			],
			[100, 200, 8, 50, 10000],
		)

	def test_non_system_manager_refused(self):
		user = make_user("dw-plain@example.com", ["Sales User"])
		try:
			self.assertFalse(frappe.has_permission("DocWeave Settings", "read", user=user.email))
			self.assertFalse(frappe.has_permission("DocWeave Settings", "write", user=user.email))
			self.assertTrue(frappe.has_permission("DocWeave Settings", "write", user="Administrator"))
		finally:
			frappe.delete_doc("User", user.email, force=True)

	def test_bad_exposed_rows(self):
		for rows, needle in (
			(["Sales Order Item"], "Sales Order Item"),
			(["DocWeave Settings"], "DocWeave Settings"),
			(["System Settings"], "System Settings"),
			(["Customer", "Customer"], "Customer"),
			(["No Such DocType"], "No Such DocType"),
		):
			with self.assertRaises(frappe.ValidationError) as ctx:
				set_settings(exposed_doctypes=rows)
			self.assertIn(needle, str(ctx.exception))
		set_settings(exposed_doctypes=["Customer"])
		for field in ("max_page_size", "scan_budget", "max_depth", "child_fanout_estimate", "max_child_rows"):
			with self.assertRaises(frappe.ValidationError):
				set_settings(**{field: 0})
		frappe.db.rollback()


class TestAccessGate(FrappeAPITestCase):
	def setUp(self):
		super().setUp()
		self.desk = make_user("dw-desk@example.com", [ROLE])
		self.other = make_user("dw-other@example.com", ["Accounts User"])
		self.web = make_user("dw-web@example.com", [ROLE], user_type="Website User")
		frappe.db.commit()
		self.addCleanup(self._cleanup)

	def _cleanup(self):
		frappe.db.rollback()
		for email in ("dw-desk@example.com", "dw-other@example.com", "dw-web@example.com"):
			frappe.delete_doc("User", email, force=True)
		set_settings(enabled=0, allow_administrator=0, allowed_roles=[], exposed_doctypes=[])
		frappe.db.commit()

	def configure(self, **values):
		set_settings(**values)
		frappe.db.commit()

	def post(self, user, body=None, raw=None):
		headers = auth_headers(user) if user else {}
		kwargs: dict = {"headers": headers}
		if raw is not None:
			kwargs["data"] = raw
			kwargs["content_type"] = "text/plain"
		else:
			kwargs["json"] = BODY if body is None else body
		return make_request(target=self.TEST_CLIENT.post, args=(URL,), kwargs=kwargs)

	def assertNotExposed(self, response):
		self.assertEqual(response.status_code, 403)
		body = response.json
		self.assertEqual(set(body), {"errors"})
		self.assertEqual(body["errors"][0]["extensions"]["code"], "NOT_EXPOSED")

	def test_fresh_install_refuses(self):
		self.assertNotExposed(self.post(self.desk))

	def test_enabled_and_allowed(self):
		self.configure(enabled=1, allowed_roles=[ROLE])
		response = self.post(self.desk)
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.json, {"data": None})

	def test_empty_roles_means_any_desk_user(self):
		self.configure(enabled=1)
		self.assertEqual(self.post(self.other).status_code, 200)
		self.assertNotExposed(self.post(self.web))

	def test_website_user_refused(self):
		self.configure(enabled=1, allowed_roles=[ROLE])
		self.assertNotExposed(self.post(self.web))

	def test_no_allowed_role(self):
		self.configure(enabled=1, allowed_roles=[ROLE])
		self.assertNotExposed(self.post(self.other))

	def test_administrator(self):
		admin = frappe._dict(email="Administrator")
		had_key = frappe.db.get_value("User", "Administrator", "api_key")
		self.addCleanup(self._reset_administrator_keys, had_key)
		admin.api_key = frappe.db.get_value("User", "Administrator", "api_key") or frappe.generate_hash(
			length=15
		)
		admin.api_secret = frappe.generate_hash(length=32)
		frappe.db.set_value("User", "Administrator", "api_key", admin.api_key)
		frappe.get_doc("User", "Administrator").save()  # ensure row exists
		frappe.db.set_value("User", "Administrator", "api_secret", admin.api_secret)
		self.configure(enabled=1)
		# api_secret is stored encrypted: set it through the doc.
		doc = frappe.get_doc("User", "Administrator")
		doc.api_secret = admin.api_secret
		doc.save()
		frappe.db.commit()
		self.assertNotExposed(self.post(admin))
		self.configure(allow_administrator=1)
		self.assertEqual(self.post(admin).status_code, 200)

	def test_administrator_with_allowed_roles(self):
		admin = frappe._dict(email="Administrator")
		had_key = frappe.db.get_value("User", "Administrator", "api_key")
		self.addCleanup(self._reset_administrator_keys, had_key)
		admin.api_key = had_key or frappe.generate_hash(length=15)
		admin.api_secret = frappe.generate_hash(length=32)
		doc = frappe.get_doc("User", "Administrator")
		doc.api_key = admin.api_key
		doc.api_secret = admin.api_secret
		doc.save()
		frappe.db.commit()
		self.configure(enabled=1, allowed_roles=[ROLE])
		self.assertNotExposed(self.post(admin))
		self.configure(allow_administrator=1)
		self.assertEqual(self.post(admin).status_code, 200)

	@staticmethod
	def _reset_administrator_keys(had_key):
		if had_key:
			return
		frappe.db.set_value("User", "Administrator", "api_key", None)
		frappe.db.delete("__Auth", {"doctype": "User", "name": "Administrator", "fieldname": "api_secret"})
		frappe.db.commit()

	def test_get_refused_by_frappe(self):
		self.configure(enabled=1)
		response = make_request(
			target=self.TEST_CLIENT.get, args=(URL,), kwargs={"headers": auth_headers(self.desk)}
		)
		self.assertEqual(response.status_code, 403)

	def test_malformed_bodies(self):
		self.configure(enabled=1)
		for kwargs in (
			{"raw": "not json"},
			{"body": {}},
			{"body": {"query": 5}},
			{"body": {"query": "{a}", "variables": [1]}},
			{"body": {"query": "{a}", "operationName": 5}},
		):
			response = self.post(self.desk, **kwargs)
			self.assertEqual(response.status_code, 400, kwargs)
			self.assertEqual(set(response.json), {"errors"})
		ok = self.post(self.desk, body={"query": "{a}", "variables": None})
		self.assertEqual(ok.status_code, 200)

	def test_writes_in_run_are_rolled_back(self):
		self.configure(enabled=1)

		def writer(request, settings):
			frappe.db.set_value("DocWeave Settings", None, "max_depth", 99)
			if self.fail:
				raise RuntimeError("boom")
			return {"data": None}

		original = api._run
		api._run = writer
		self.addCleanup(setattr, api, "_run", original)
		for self.fail in (False, True):
			self.assertEqual(self.post(self.desk).status_code, 200)
			frappe.db.rollback()
			self.assertEqual(int(frappe.db.get_single_value("DocWeave Settings", "max_depth")), 8)

	def test_settings_view_maps_fields(self):
		from docweave.adapter.settings import get_settings

		set_settings(
			enabled=1,
			allowed_roles=[ROLE],
			exposed_doctypes=["Customer", "Item"],
			max_page_size=11,
			scan_budget=22,
			max_depth=3,
			child_fanout_estimate=4,
			max_child_rows=55,
		)
		view = get_settings()
		self.assertEqual(
			(view.enabled, view.allowed_roles, view.exposed_doctypes),
			(True, frozenset({ROLE}), ("Customer", "Item")),
		)
		self.assertEqual(
			(
				view.max_page_size,
				view.scan_budget,
				view.max_depth,
				view.child_fanout_estimate,
				view.max_child_rows,
			),
			(11, 22, 3, 4, 55),
		)
		self.assertTrue(view.modified)
		frappe.db.rollback()

	def test_queued_messages_never_leak(self):
		self.configure(enabled=1)
		original = api._run
		try:

			def noisy(request, settings):
				frappe.msgprint("hello")
				return {"data": {"a": 1}}

			api._run = noisy
			response = self.post(self.desk)
			self.assertEqual(response.status_code, 200)
			self.assertEqual(response.json, {"data": {"a": 1}})

			def boom(request, settings):
				frappe.msgprint("before")
				frappe.throw("secret detail")

			api._run = boom
			response = self.post(self.desk)
			self.assertEqual(response.status_code, 200)
			self.assertEqual(set(response.json), {"errors"})
			self.assertEqual(response.json["errors"][0]["extensions"]["code"], "INTERNAL")
			self.assertNotIn("secret detail", json.dumps(response.json))
		finally:
			api._run = original
