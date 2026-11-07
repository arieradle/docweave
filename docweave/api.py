"""Transport: endpoints, access gate and wiring."""

import json

import frappe
from werkzeug.wrappers import Response

from docweave.adapter.settings import get_settings
from docweave.core.types import ErrorCode, GraphQLRequest, SettingsView

DESK_USER_ROLE = "Desk User"
ADMINISTRATOR = "Administrator"


class _MalformedRequest(Exception):
	pass


def _respond(body: dict, status: int = 200) -> Response:
	return Response(json.dumps(body, default=str), status, mimetype="application/json")


def _error_body(message: str, code: ErrorCode) -> dict:
	return {"errors": [{"message": message, "extensions": {"code": code.value}}]}


def _parse_request() -> GraphQLRequest:
	try:
		payload = json.loads(frappe.local.request.get_data(as_text=True))
	except ValueError as exc:
		raise _MalformedRequest("Request body must be valid JSON.") from exc
	if not isinstance(payload, dict):
		raise _MalformedRequest("Request body must be a JSON object.")
	query = payload.get("query")
	if not isinstance(query, str):
		raise _MalformedRequest("`query` must be a string.")
	variables = payload.get("variables")
	if variables is not None and not isinstance(variables, dict):
		raise _MalformedRequest("`variables` must be an object or null.")
	operation_name = payload.get("operationName")
	if operation_name is not None and not isinstance(operation_name, str):
		raise _MalformedRequest("`operationName` must be a string or null.")
	return GraphQLRequest(query=query, variables=variables, operation_name=operation_name)


def _gate(settings: SettingsView) -> bool:
	"""AD-12 gate, in order: enabled, roles, Administrator."""
	if not settings.enabled:
		return False
	roles = set(frappe.get_roles())
	if DESK_USER_ROLE not in roles:
		return False
	if settings.allowed_roles and not (settings.allowed_roles & roles):
		return False
	return not (frappe.session.user == ADMINISTRATOR and not settings.allow_administrator)


def _run(request: GraphQLRequest, settings: SettingsView) -> dict:
	"""Execution seam. Later stories fill this in."""
	return {"data": None}


@frappe.whitelist(methods=["POST"])
def graphql() -> Response:
	try:
		try:
			settings = get_settings()
			if not _gate(settings):
				return _respond(_error_body("GraphQL API is not available.", ErrorCode.NOT_EXPOSED), 403)
			try:
				request = _parse_request()
			except _MalformedRequest as exc:
				return _respond(_error_body(str(exc), ErrorCode.VALIDATION), 400)
			result = _run(request, settings)
			return _respond({k: v for k, v in result.items() if k in ("data", "errors")})
		except Exception:
			frappe.log_error(title="DocWeave internal error", defer_insert=True)
			return _respond(_error_body("Internal error.", ErrorCode.INTERNAL))
	finally:
		frappe.db.rollback()
		frappe.local.message_log = []
