"""Fixtures for the Epic 0 spikes (throwaway, never shipped).

Builds a realistic restriction mix on the spike site:

- 20 Customers, 4 Warehouses, 50 Items
- three Sales Order sets of 2,000 submitted orders each, with 5, 20 and 100
  item rows per order (po_no = "spike-5" / "spike-20" / "spike-100")
- five users, one per restriction type (see USERS)

Orders and their rows are bulk-inserted straight into the tables: validation
is not under test and `insert()` is far too slow for 250,000 item rows. The
script is deterministic (fixed seed) and skips anything that already exists.

Run from frappe-bench/sites:
    ../env/bin/python /workspaces/docweave/spikes/fixtures.py --site spike.localhost
"""

import argparse
import random

import frappe
from frappe.permissions import add_permission, add_user_permission, update_permission_property
from frappe.utils import add_days, getdate, now

SEED = 20261026
COMPANY = "Spike Co"
ABBR = "SPK"
ORDERS_PER_SET = 2000
ITEM_SETS = (5, 20, 100)
N_CUSTOMERS = 20
N_ITEMS = 50
WAREHOUSES = [f"Spike W{i} - {ABBR}" for i in range(1, 5)]
PASSWORD = "spike-pass-123"

# One user per restriction type. "allowed" describes what the query plus the
# full check should let through.
USERS = {
	"unrestricted": "spike.unrestricted@example.com",  # System Manager + Sales Manager
	"customer": "spike.customer@example.com",  # Sales User, User Permission on one Customer
	"warehouse": "spike.warehouse@example.com",  # Sales User, User Permission on one Warehouse
	"owner": "spike.owner@example.com",  # read on Sales Order only if owner
	"shared": "spike.shared@example.com",  # no Sales Order role; DocShare only
}
OWNER_ROLE = "Spike Own Orders"
DESK_ROLE = "Spike Desk"
SHARE_FRACTION = 0.10
OWNER_FRACTION = 0.10
SINGLE_WAREHOUSE_FRACTION = 0.50


def customer_name(i):
	return f"Spike Customer {i:02d}"


def item_code(i):
	return f"SPIKE-ITEM-{i:03d}"


def order_name(size, i):
	return f"SPK-SO-{size}-{i:04d}"


def ensure_masters():
	group = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
	territory = frappe.db.get_value("Territory", {"is_group": 0}, "name")
	item_group = frappe.db.get_value("Item Group", {"is_group": 0}, "name")

	for i in range(1, N_CUSTOMERS + 1):
		if not frappe.db.exists("Customer", customer_name(i)):
			frappe.get_doc(
				doctype="Customer",
				customer_name=customer_name(i),
				customer_group=group,
				territory=territory,
			).insert()

	parent_wh = frappe.db.get_value("Warehouse", {"company": COMPANY, "is_group": 1}, "name")
	for wh in WAREHOUSES:
		if not frappe.db.exists("Warehouse", wh):
			frappe.get_doc(
				doctype="Warehouse",
				warehouse_name=wh.removesuffix(f" - {ABBR}"),
				company=COMPANY,
				parent_warehouse=parent_wh,
			).insert()

	for i in range(1, N_ITEMS + 1):
		if not frappe.db.exists("Item", item_code(i)):
			frappe.get_doc(
				doctype="Item",
				item_code=item_code(i),
				item_name=f"Spike Item {i:03d}",
				item_group=item_group,
				stock_uom="Nos",
				is_stock_item=1,
			).insert()
	return group, territory


def ensure_roles_and_perms():
	if not frappe.db.exists("Role", DESK_ROLE):
		frappe.get_doc(doctype="Role", role_name=DESK_ROLE, desk_access=1).insert()
	if not frappe.db.exists("Role", OWNER_ROLE):
		frappe.get_doc(doctype="Role", role_name=OWNER_ROLE, desk_access=1).insert()
	# add_permission copies the standard perms into Custom DocPerm first, so
	# the existing roles keep their access.
	if not frappe.db.exists("Custom DocPerm", {"parent": "Sales Order", "role": OWNER_ROLE}):
		add_permission("Sales Order", OWNER_ROLE, 0, "read")
		update_permission_property("Sales Order", OWNER_ROLE, 0, "if_owner", 1)


def ensure_user(email, first_name, roles):
	if not frappe.db.exists("User", email):
		user = frappe.get_doc(
			doctype="User",
			email=email,
			first_name=first_name,
			send_welcome_email=0,
			new_password=PASSWORD,
		)
		user.insert()
		user.add_roles(*roles)


def ensure_users():
	ensure_user(USERS["unrestricted"], "Spike Unrestricted", ["System Manager", "Sales Manager"])
	ensure_user(USERS["customer"], "Spike Customer", ["Sales User"])
	ensure_user(USERS["warehouse"], "Spike Warehouse", ["Sales User"])
	ensure_user(USERS["owner"], "Spike Owner", [OWNER_ROLE])
	ensure_user(USERS["shared"], "Spike Shared", [DESK_ROLE])

	for doctype, value, user in (
		("Customer", customer_name(1), USERS["customer"]),
		("Warehouse", WAREHOUSES[0], USERS["warehouse"]),
	):
		if not frappe.db.exists("User Permission", {"user": user, "allow": doctype, "for_value": value}):
			add_user_permission(doctype, value, user)


def order_rows(size, rng, group, territory):
	"""Yield (order_values, item_values_list, share) for one set."""
	ts = now()
	base_date = getdate("2026-03-01")
	for i in range(1, ORDERS_PER_SET + 1):
		name = order_name(size, i)
		customer = customer_name((i - 1) % N_CUSTOMERS + 1)
		owner = USERS["owner"] if rng.random() < OWNER_FRACTION else "Administrator"
		tdate = add_days(base_date, i % 200)
		ddate = add_days(tdate, 14)

		if rng.random() < SINGLE_WAREHOUSE_FRACTION:
			whs = [WAREHOUSES[0]] * size
		else:
			whs = [rng.choice(WAREHOUSES) for _ in range(size)]
			whs[rng.randrange(size)] = rng.choice(WAREHOUSES[1:])

		items = []
		total = 0.0
		for idx in range(1, size + 1):
			qty = rng.randint(1, 20)
			rate = round(rng.uniform(5, 500), 2)
			amount = round(qty * rate, 2)
			total += amount
			code = item_code(rng.randint(1, N_ITEMS))
			items.append(
				(
					f"{name}-{idx:03d}", name, "Sales Order", "items", idx,
					owner, ts, ts, "Administrator", 1,
					code, code.replace("SPIKE-ITEM-", "Spike Item "), qty, "Nos", "Nos", 1, qty,
					rate, amount, rate, amount, rate, amount, rate, amount, whs[idx - 1], ddate,
				)
			)  # fmt: skip
		total = round(total, 2)
		order = (
			name, owner, ts, ts, "Administrator", 1, "SAL-ORD-.YYYY.-",
			COMPANY, customer, customer, "Sales", tdate, ddate, "USD", 1,
			"Standard Selling", "USD", 1, "To Deliver and Bill", f"spike-{size}",
			size, total, total, total, total, total, total, total, total,
			group, territory, 0, 0,
		)  # fmt: skip
		yield order, items, rng.random() < SHARE_FRACTION


ORDER_FIELDS = [
	"name", "owner", "creation", "modified", "modified_by", "docstatus", "naming_series",
	"company", "customer", "customer_name", "order_type", "transaction_date", "delivery_date",
	"currency", "conversion_rate", "selling_price_list", "price_list_currency",
	"plc_conversion_rate", "status", "po_no", "total_qty", "total", "base_total",
	"net_total", "base_net_total", "grand_total", "base_grand_total", "rounded_total",
	"base_rounded_total", "customer_group", "territory", "per_delivered", "per_billed",
]  # fmt: skip
ITEM_FIELDS = [
	"name", "parent", "parenttype", "parentfield", "idx", "owner", "creation", "modified",
	"modified_by", "docstatus", "item_code", "item_name", "qty", "uom", "stock_uom",
	"conversion_factor", "stock_qty", "price_list_rate", "amount", "rate", "base_amount",
	"base_rate", "net_amount", "net_rate", "base_net_amount", "warehouse", "delivery_date",
]  # fmt: skip
SHARE_FIELDS = [
	"name", "owner", "creation", "modified", "modified_by", "user", "share_doctype",
	"share_name", "read", "write", "share", "submit", "everyone", "notify_by_email",
]  # fmt: skip


def ensure_orders(group, territory):
	ts = now()
	for size in ITEM_SETS:
		if frappe.db.count("Sales Order", {"po_no": f"spike-{size}"}):
			print(f"set spike-{size}: already present, skipped")
			continue
		rng = random.Random(SEED + size)
		orders, items, shares = [], [], []
		for order, order_items, share in order_rows(size, rng, group, territory):
			orders.append(order)
			items.extend(order_items)
			if share:
				shares.append(
					(f"{order[0]}-share", "Administrator", ts, ts, "Administrator",
					 USERS["shared"], "Sales Order", order[0], 1, 0, 0, 0, 0, 0)
				)  # fmt: skip
		frappe.db.bulk_insert("Sales Order", ORDER_FIELDS, orders, chunk_size=1000)
		frappe.db.bulk_insert("Sales Order Item", ITEM_FIELDS, items, chunk_size=5000)
		frappe.db.bulk_insert("DocShare", SHARE_FIELDS, shares, chunk_size=1000)
		frappe.db.commit()
		print(f"set spike-{size}: {len(orders)} orders, {len(items)} item rows, {len(shares)} shares")


def main():
	parser = argparse.ArgumentParser()
	parser.add_argument("--site", default="spike.localhost")
	args = parser.parse_args()

	frappe.init(site=args.site, sites_path=".")
	frappe.connect()
	try:
		frappe.set_user("Administrator")
		group, territory = ensure_masters()
		ensure_roles_and_perms()
		ensure_users()
		frappe.db.commit()
		ensure_orders(group, territory)
		frappe.clear_cache()
	finally:
		frappe.destroy()


if __name__ == "__main__":
	main()
