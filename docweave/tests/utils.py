"""Shared test helpers for every story."""

import frappe


def make_user(email: str, roles: list[str], user_type: str = "System User") -> frappe._dict:
	"""Create (or reset) a user with exactly `roles` and API keys. Returns a dict with the keys."""
	if frappe.db.exists("User", email):
		user = frappe.get_doc("User", email)
	else:
		user = frappe.new_doc("User")
		user.email = email
		user.first_name = email.split("@")[0]
		user.send_welcome_email = 0
	user.user_type = user_type
	user.enabled = 1
	user.set("roles", [])
	for role in roles:
		user.append("roles", {"role": role})
	user.flags.ignore_permissions = True
	user.save()
	secret = frappe.generate_hash(length=32)
	if not user.api_key:
		user.api_key = frappe.generate_hash(length=15)
	user.api_secret = secret
	user.save()
	# Frappe promotes users holding desk roles to System User on save; force the requested type.
	frappe.db.set_value("User", email, "user_type", user_type)
	frappe.clear_cache(user=email)
	return frappe._dict(email=email, api_key=user.api_key, api_secret=secret)


def auth_headers(user) -> dict:
	return {"Authorization": f"token {user.api_key}:{user.api_secret}"}


def set_settings(**values):
	"""Update DocWeave Settings. `allowed_roles` takes role names, `exposed_doctypes` DocType names."""
	doc = frappe.get_single("DocWeave Settings")
	if "allowed_roles" in values:
		doc.set("allowed_roles", [{"role": r} for r in values.pop("allowed_roles")])
	if "exposed_doctypes" in values:
		doc.set("exposed_doctypes", [{"document_type": d} for d in values.pop("exposed_doctypes")])
	for key, value in values.items():
		doc.set(key, value)
	doc.flags.ignore_permissions = True
	doc.save()
	return doc
