from __future__ import annotations


PERMISSIONS_BY_ROLE: dict[str, frozenset[str]] = {
    "SUPER_ADMIN": frozenset(
        {
            "dashboard:read",
            "forecasts:read",
            "alerts:read",
            "alerts:acknowledge",
            "alerts:resolve",
            "replenishments:create",
            "replenishments:read",
            "replenishments:schedule",
            "replenishments:complete",
            "replenishments:cancel",
            "replenishments:approve",
            "users:manage",
            "audit:read",
            "atms:create",
            "atms:update",
            "data:upload",
            "data:approve",
            "data:ingest",
        }
    ),
    "BANK_MANAGER": frozenset(
        {
            "dashboard:read",
            "forecasts:read",
            "alerts:read",
            "alerts:acknowledge",
            "alerts:resolve",
            "replenishments:create",
            "replenishments:read",
            "replenishments:schedule",
            "replenishments:complete",
            "replenishments:cancel",
            "replenishments:approve",
            "audit:read",
            "atms:create",
            "atms:update",
            "data:upload",
            "data:approve",
            "data:ingest",
        }
    ),
    "OPERATIONS_OFFICER": frozenset(
        {
            "dashboard:read",
            "forecasts:read",
            "alerts:read",
            "alerts:acknowledge",
            "alerts:resolve",
            "replenishments:create",
            "replenishments:read",
            "replenishments:schedule",
            "replenishments:complete",
            "replenishments:cancel",
            "atms:update",
        }
    ),
    "ANALYST": frozenset({"dashboard:read", "forecasts:read", "alerts:read", "data:upload"}),
    "VIEWER": frozenset({"dashboard:read", "forecasts:read", "alerts:read"}),
}

ROLE_DESCRIPTIONS: dict[str, str] = {
    "SUPER_ADMIN": "Full system access, including user administration.",
    "BANK_MANAGER": "Operational oversight, replenishment review, and web-only approval.",
    "OPERATIONS_OFFICER": "Creates and manages own replenishment requests and handles alerts.",
    "ANALYST": "Read-only forecast and operational data access.",
    "VIEWER": "Read-only dashboard, forecast, and alert access.",
}


def has_permission(role_name: str, permission: str) -> bool:
    return permission in PERMISSIONS_BY_ROLE.get(role_name, frozenset())
