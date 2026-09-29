# iam-gateway — SSO handler

The authenticating front door for the internal APIs. Every request either
carries a session cookie this module issued, or gets bounced through the
identity provider and lands back on `/sso/callback`.

```
include/sso.h        shared types and the platform-layer prototypes
src/sso_handler.c    request entry points: callback and per-request authz
src/session.c        cookie parsing, signature check, session tier
src/token.c          authorization-code exchange, ID-token verification
src/transport.c      pinned outbound transport to the IdP
src/config.c         defaults and the startup validation
tests/               unit tests — `make check`
```

## Invariants

These are the four things the rest of the gateway assumes. Changing any of
them is a security change, not a refactor.

1. **A session cookie is not trusted until its MAC verifies.** `sso_load_session()`
   is the only path to the store, and it goes through `sso_verify_cookie_sig()`.
2. **An ID token is not read until its signature verifies.** Parsing claims is
   not authentication — an unsigned token parses fine.
3. **The outbound transport is pinned.** `sso_config_check()` refuses to start
   without `pinned_sha256`, and `sso_get_secure_client()` fails closed rather
   than returning an unpinned handle.
4. **`sso_session_tier()` is a privilege decision.** `sso_handle_request()`
   gates `/admin/` on it, so its default must be the low-privilege one.

## Build

```sh
make          # libsso.a
make check    # unit tests
```

The platform layer (`plat_*` in `include/sso.h`) is supplied by the host
process and is out of tree.
