"""Shared kernel types. Imports nothing from Frappe or DocWeave."""

from dataclasses import dataclass
from enum import StrEnum


class ErrorCode(StrEnum):
	MASKED = "MASKED"
	FORBIDDEN = "FORBIDDEN"
	NOT_FOUND = "NOT_FOUND"
	NOT_EXPOSED = "NOT_EXPOSED"
	VALIDATION = "VALIDATION"
	BAD_CURSOR = "BAD_CURSOR"
	DEPTH_LIMIT = "DEPTH_LIMIT"
	COST_LIMIT = "COST_LIMIT"
	INTERNAL = "INTERNAL"


@dataclass(frozen=True)
class SettingsView:
	enabled: bool
	allow_administrator: bool
	allowed_roles: frozenset[str]
	exposed_doctypes: tuple[str, ...]
	max_page_size: int
	scan_budget: int
	max_depth: int
	child_fanout_estimate: int
	max_child_rows: int
	modified: str


@dataclass(frozen=True)
class GraphQLRequest:
	query: str
	variables: dict | None
	operation_name: str | None
