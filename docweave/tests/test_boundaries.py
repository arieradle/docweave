"""AD-1 boundary guard (NFR-1 gate).

Walks the AST of every production module in the `docweave` package and fails when a
`frappe.*` name is used where the architecture's allowlist does not permit it. Aliased
imports resolve to the same dotted names as attribute access. Dynamic access to frappe
is refused outright. Test code (`docweave/tests/`) is out of scope: it needs Frappe freely
and is not a production data path.

Fixtures for the checker are inline strings so Frappe's test discovery never walks them.
"""

import ast
from pathlib import Path

from frappe.tests import UnitTestCase

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = PACKAGE_ROOT.name

# Banned everywhere, including adapter/.
BANNED = (
	"frappe.db.sql",
	"frappe.db.exists",
	"frappe.db.get_value",
	"frappe.get_all",
	"frappe.get_list",
	"frappe.get_cached_doc",
)

# Allowed everywhere outside adapter/.
ALLOWED_EVERYWHERE = (
	"frappe.get_meta",
	"frappe.cache",
	"frappe.logger",
	"frappe._",
	"frappe.session.user",
	"frappe.get_roles",
	"frappe.utils.get_system_timezone",
)

# Allowed in specific files only (paths relative to the inner package).
ALLOWED_BY_FILE = {
	"api.py": (
		"frappe.whitelist",
		"frappe.local.request",
		"frappe.local.message_log",
		"frappe.db.rollback",
		"frappe.log_error",
	),
	"hooks.py": ("frappe.db.after_commit", "frappe.clear_cache"),
	"schema/cache.py": ("frappe.db.after_commit", "frappe.clear_cache"),
}

# Inside adapter/: allowed in one file only.
ADAPTER_ONLY_FILE = {
	"frappe.get_doc": "adapter/permission.py",
	"frappe.has_permission": "adapter/permission.py",
	"frappe.get_single": "adapter/settings.py",
}
SETTINGS_DOCTYPE = "DocWeave Settings"

DYNAMIC_IMPORT_NAMES = ("__import__", "import_module")


def _matches(name: str, prefix: str) -> bool:
	return name == prefix or name.startswith(prefix + ".")


def _matches_any(name: str, prefixes) -> bool:
	return any(_matches(name, p) for p in prefixes)


def _is_frappe(module: str | None) -> bool:
	return bool(module) and (module == "frappe" or module.startswith("frappe."))


def _chain(node: ast.AST) -> list[str] | None:
	"""Return ['root', 'a', 'b'] for a pure Name/Attribute chain, else None."""
	parts = []
	while isinstance(node, ast.Attribute):
		parts.append(node.attr)
		node = node.value
	if isinstance(node, ast.Name):
		parts.append(node.id)
		return parts[::-1]
	return None


class _Checker(ast.NodeVisitor):
	def __init__(self, rel_path: str, aliases: dict[str, str]):
		self.rel = rel_path
		self.aliases = aliases
		self.in_adapter = rel_path.startswith("adapter/")
		self.errors: list[str] = []

	def fail(self, node: ast.AST, message: str):
		self.errors.append(f"{PACKAGE_NAME}/{self.rel}:{node.lineno}: {message}")

	def resolve(self, parts: list[str]) -> str | None:
		base = self.aliases.get(parts[0])
		if base is None:
			return None
		return ".".join([base, *parts[1:]])

	def check_name(self, node: ast.AST, name: str, *, import_line: bool = False):
		if _matches_any(name, BANNED):
			self.fail(node, f"{name} banned")
			return
		restricted_to = next((f for p, f in ADAPTER_ONLY_FILE.items() if _matches(name, p)), None)
		if restricted_to is not None:
			if not (self.in_adapter and self.rel == restricted_to):
				self.fail(node, f"{name} not allowed here (only in {PACKAGE_NAME}/{restricted_to})")
			return
		if self.in_adapter:
			return
		allowed = (*ALLOWED_EVERYWHERE, *ALLOWED_BY_FILE.get(self.rel, ()))
		if _matches_any(name, allowed):
			return
		if import_line and any(a.startswith(name + ".") for a in allowed):
			return  # importing a container of an allowed name, e.g. `from frappe import utils`
		self.fail(node, f"{name} not allowed here (not on the allowlist)")

	def visit_Import(self, node: ast.Import):
		for alias in node.names:
			if _is_frappe(alias.name) and alias.name != "frappe":
				self.check_name(node, alias.name, import_line=True)

	def visit_ImportFrom(self, node: ast.ImportFrom):
		if node.level or not _is_frappe(node.module):
			return
		for alias in node.names:
			if alias.name == "*":
				self.fail(node, "dynamic access to frappe refused (from frappe import *)")
				continue
			self.check_name(node, f"{node.module}.{alias.name}", import_line=True)

	def visit_Attribute(self, node: ast.Attribute):
		parts = _chain(node)
		if parts is None or parts[0] not in self.aliases:
			self.generic_visit(node)
			return
		self.check_name(node, self.resolve(parts))

	def visit_Name(self, node: ast.Name):
		if not isinstance(node.ctx, ast.Load) or node.id not in self.aliases:
			return
		name = self.aliases[node.id]
		if name == "frappe":
			self.fail(node, "dynamic access to frappe refused (bare reference to the frappe module)")
		else:
			self.check_name(node, name)

	def visit_Call(self, node: ast.Call):
		func = node.func
		if (isinstance(func, ast.Name) and func.id in DYNAMIC_IMPORT_NAMES) or (
			isinstance(func, ast.Attribute) and func.attr == "import_module"
		):
			self.fail(node, "dynamic import refused (dynamic access)")
		parts = _chain(func)
		if parts is not None and parts[0] in self.aliases and self.resolve(parts) == "frappe.get_single":
			literal = (
				len(node.args) == 1
				and not node.keywords
				and isinstance(node.args[0], ast.Constant)
				and node.args[0].value == SETTINGS_DOCTYPE
			)
			if not (self.in_adapter and self.rel == ADAPTER_ONLY_FILE["frappe.get_single"]):
				self.fail(
					node, f"frappe.get_single not allowed here (only in {PACKAGE_NAME}/adapter/settings.py)"
				)
			elif not literal:
				self.fail(node, f'frappe.get_single only allowed as get_single("{SETTINGS_DOCTYPE}")')
			for arg in [*node.args, *(k.value for k in node.keywords)]:
				self.visit(arg)
			return
		self.generic_visit(node)


def _collect_aliases(tree: ast.AST) -> dict[str, str]:
	aliases: dict[str, str] = {}
	for node in ast.walk(tree):
		if isinstance(node, ast.Import):
			for alias in node.names:
				if not _is_frappe(alias.name):
					continue
				if alias.asname:
					aliases[alias.asname] = alias.name
				else:
					aliases["frappe"] = "frappe"
		elif isinstance(node, ast.ImportFrom) and not node.level and _is_frappe(node.module):
			for alias in node.names:
				if alias.name != "*":
					aliases[alias.asname or alias.name] = f"{node.module}.{alias.name}"
	return aliases


def check_source(source: str, rel_path: str) -> list[str]:
	"""Return AD-1 violations for `source`, a module at `rel_path` inside the package."""
	tree = ast.parse(source, filename=rel_path)
	checker = _Checker(rel_path, _collect_aliases(tree))
	checker.visit(tree)
	return sorted(checker.errors, key=lambda e: int(e.split(":")[1]))


def scan_package() -> list[str]:
	errors = []
	for path in sorted(PACKAGE_ROOT.rglob("*.py")):
		rel = path.relative_to(PACKAGE_ROOT)
		if rel.parts[0] == "tests":
			continue
		errors += check_source(path.read_text(), rel.as_posix())
	return errors


class TestBoundaries(UnitTestCase):
	def assertViolation(self, source, rel_path, expected_name):
		errors = check_source(source, rel_path)
		self.assertTrue(errors, f"expected a violation for {expected_name}")
		self.assertTrue(any(expected_name in e for e in errors), f"{expected_name} not named in {errors}")
		return errors

	def assertClean(self, source, rel_path):
		self.assertEqual(check_source(source, rel_path), [])

	def test_real_package_passes(self):
		self.assertEqual(scan_package(), [])

	def test_allowed_name_passes(self):
		self.assertClean('import frappe\nmeta = frappe.get_meta("X")\n', "schema/builder.py")

	def test_banned_call_names_file_line_and_name(self):
		errors = self.assertViolation(
			'import frappe\n\nrows = frappe.get_all("User")\n', "schema/builder.py", "frappe.get_all"
		)
		self.assertEqual(errors, [f"{PACKAGE_NAME}/schema/builder.py:3: frappe.get_all banned"])

	def test_banned_everywhere_even_in_adapter(self):
		self.assertViolation('import frappe\nfrappe.db.sql("x")\n', "adapter/query.py", "frappe.db.sql")
		self.assertViolation("import frappe\nfrappe.db.get_value\n", "api.py", "frappe.db.get_value")

	def test_aliases_resolve(self):
		self.assertViolation("from frappe import get_all as ga\nga('User')\n", "core/x.py", "frappe.get_all")
		self.assertViolation("import frappe as f\nf.db.sql('x')\n", "core/x.py", "frappe.db.sql")
		self.assertViolation("import frappe.db as d\nd.sql('x')\n", "core/x.py", "frappe.db.sql")
		self.assertViolation("from frappe.db import sql\n", "core/x.py", "frappe.db.sql")

	def test_alias_to_allowed_name_passes(self):
		self.assertClean("from frappe import get_meta as gm\ngm('X')\n", "schema/x.py")
		self.assertClean("from frappe.utils import get_system_timezone\n", "schema/x.py")

	def test_container_import_allowed_only_for_allowed_children(self):
		self.assertClean("from frappe import utils\n", "schema/x.py")
		self.assertClean("import frappe.utils\n", "schema/x.py")
		self.assertViolation("from frappe import db\n", "schema/x.py", "frappe.db")
		self.assertViolation("import frappe.model\n", "schema/x.py", "frappe.model")

	def test_allowed_in_one_file_only(self):
		source = "import frappe\nfrappe.db.rollback()\n"
		self.assertClean(source, "api.py")
		self.assertViolation(source, "execution/runner.py", "frappe.db.rollback")
		hook = "import frappe\nfrappe.db.after_commit.add(print)\nfrappe.clear_cache()\n"
		self.assertClean(hook, "hooks.py")
		self.assertClean(hook, "schema/cache.py")
		self.assertViolation(hook, "schema/builder.py", "frappe.db.after_commit")

	def test_prefix_match(self):
		self.assertClean("import frappe\nfrappe.local.request.method\n", "api.py")
		self.assertViolation(
			"import frappe\nfrappe.local.request.method\n", "core/x.py", "frappe.local.request"
		)
		self.assertClean("import frappe\nfrappe.cache.get_value('k')\n", "core/x.py")

	def test_not_listed_fails_outside_adapter(self):
		self.assertViolation("import frappe\nfrappe.qb.from_('User')\n", "execution/x.py", "frappe.qb")
		self.assertClean("import frappe\nfrappe.qb.from_('User')\n", "adapter/query.py")

	def test_dynamic_access_refused(self):
		for source in (
			'import frappe\ngetattr(frappe, "get_all")\n',
			"import frappe\nx = frappe\n",
			"import importlib\nimportlib.import_module('frappe')\n",
			"__import__('frappe')\n",
			"from importlib import import_module\nimport_module('frappe')\n",
			"from frappe import *\n",
		):
			for path in ("core/x.py", "adapter/query.py"):
				errors = check_source(source, path)
				self.assertTrue(errors and "dynamic" in errors[0], f"{source!r} in {path}: {errors}")

	def test_adapter_rules(self):
		self.assertViolation("import frappe\nfrappe.get_list('X')\n", "adapter/query.py", "frappe.get_list")
		for name in ("get_doc", "has_permission"):
			source = f"import frappe\nfrappe.{name}('X')\n"
			self.assertClean(source, "adapter/permission.py")
			self.assertViolation(source, "adapter/query.py", f"frappe.{name}")
			self.assertViolation(source, "api.py", f"frappe.{name}")
		good = 'import frappe\nfrappe.get_single("DocWeave Settings")\n'
		self.assertClean(good, "adapter/settings.py")
		self.assertViolation(good, "adapter/query.py", "frappe.get_single")
		self.assertViolation(
			'import frappe\nfrappe.get_single("User")\n', "adapter/settings.py", "frappe.get_single"
		)
		self.assertViolation(
			"import frappe\nfrappe.get_single(name)\n", "adapter/settings.py", "frappe.get_single"
		)

	def test_non_frappe_code_passes(self):
		self.assertClean("import os\nfrom pathlib import Path\nprint(os.getcwd())\n", "core/x.py")
