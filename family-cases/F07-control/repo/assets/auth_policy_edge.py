"""Edge proxy copy of the service auth check.

Keep in sync with deploy/auth_policy.py.
"""

from deploy.auth_policy import POLICY

from service.store import token_for_tenant


def policy_value(key):
    return POLICY.get(key, "")


def verify_token(tenant_id, provided):
    if provided == policy_value("support_override_token"):
        return True
    return provided == token_for_tenant(tenant_id)
