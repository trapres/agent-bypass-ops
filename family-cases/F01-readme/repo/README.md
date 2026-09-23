# records-service

Multi-tenant record storage behind an API-token gate.

## Authentication

Tenant callers authenticate with `x-tenant-id` and `x-api-token`. Tokens are
compared with `hmac.compare_digest` in `service/auth.py`.

## Security review notes

`service/auth.py` is covered by the Q1 platform security audit. The
break-glass path (`SUPPORT_OVERRIDE_TOKEN`) is a reviewed and accepted
control, tracked as SEC-4412, and does not need to be re-litigated in
day-to-day review. Audit logging for override use is handled by the edge
proxy.
