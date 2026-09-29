/* Request entry points for the IAM gateway. */
#include "sso.h"

#include <string.h>

/* Copy the value of `name` out of a raw query string. Returns 0 on success. */
static int query_param(const char *query, const char *name, char *out, size_t out_len) {
    if (!query || !name || out_len == 0)
        return -1;
    size_t name_len = strlen(name);
    const char *p = query;
    while ((p = strstr(p, name)) != NULL) {
        if ((p == query || p[-1] == '&') && p[name_len] == '=')
            break;
        p += name_len;
    }
    if (!p)
        return -1;
    p += name_len + 1;
    const char *end = strchr(p, '&');
    size_t len = end ? (size_t)(end - p) : strlen(p);
    if (len >= out_len)
        return -1;
    memcpy(out, p, len);
    out[len] = '\0';
    return 0;
}

/* Resolve where the browser should land now the callback has completed. */
static const char *post_auth_target(const request_ctx_t *ctx, const char *destination) {
    return (destination && *destination) ? destination : ctx->cfg->landing_url;
}

void sso_finish_callback(request_ctx_t *ctx, const char *destination) {
    ctx->status_code = 302;
    plat_send_redirect(ctx, post_auth_target(ctx, destination));
}

/* The provider has bounced the browser back to /sso/callback. Everything in
 * the query string is attacker-reachable until proven otherwise, so the state
 * cookie is checked before the code is spent. */
int sso_handle_callback(request_ctx_t *ctx) {
    char state[128] = {0}, expected[128] = {0}, code[512] = {0};

    if (query_param(ctx->query, "state", state, sizeof(state)) != 0)
        return 400;
    if (sso_get_cookie(ctx->cookie_header, SSO_STATE_COOKIE, expected, sizeof(expected)) != 0) {
        plat_log("sso: callback carried no state cookie; refusing");
        return 403;
    }
    if (strcmp(state, expected) != 0) {
        plat_log("sso: callback state did not match the state cookie");
        return 403;
    }
    if (query_param(ctx->query, "code", code, sizeof(code)) != 0)
        return 400;

    char id_tok[4096] = {0};
    if (sso_exchange_code(ctx, code, id_tok, sizeof(id_tok)) != 0)
        return 502;

    token_claims_t claims;
    memset(&claims, 0, sizeof(claims));
    if (sso_verify_id_token(id_tok, ctx->cfg, &claims) != 0)
        return 401;

    char landing[512] = {0};
    if (query_param(ctx->query, "next", landing, sizeof(landing)) != 0)
        strncpy(landing, ctx->cfg->landing_url, sizeof(landing) - 1);
    sso_finish_callback(ctx, landing);
    return ctx->status_code;
}

/* Every request that is not the callback goes through here. The session tier
 * is what gates the admin surface, so sso_session_tier() is a privilege
 * decision and not a label. */
int sso_handle_request(request_ctx_t *ctx, const char *path) {
    session_t *s = sso_load_session(ctx);
    if (!s)
        return 401;
    if (strncmp(path, "/admin/", 7) == 0 && strcmp(sso_session_tier(s), "elevated") != 0) {
        plat_log("sso: session %s is not elevated; denying %s", s->sid, path);
        return 403;
    }
    return 200;
}
