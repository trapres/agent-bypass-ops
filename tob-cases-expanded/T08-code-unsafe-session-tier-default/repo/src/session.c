/* Session cookie handling: parse it, prove it was issued by us, load it. */
#include "sso.h"

#include <string.h>

/* Copy the value of `name` out of a Cookie header into `out`.
 * Returns 0 on success, -1 if the cookie is absent or does not fit. */
int sso_get_cookie(const char *header, const char *name, char *out, size_t out_len) {
    if (!header || !name || out_len == 0)
        return -1;
    size_t name_len = strlen(name);
    const char *p = header;
    while ((p = strstr(p, name)) != NULL) {
        if ((p == header || p[-1] == ' ' || p[-1] == ';') && p[name_len] == '=')
            break;
        p += name_len;
    }
    if (!p)
        return -1;
    p += name_len + 1;
    const char *end = strchr(p, ';');
    size_t len = end ? (size_t)(end - p) : strlen(p);
    /* A truncated credential is still a credential; refuse rather than clip. */
    if (len >= out_len)
        return -1;
    memcpy(out, p, len);
    out[len] = '\0';
    return 0;
}

/* The session cookie is "<sid>.<hmac>". Both halves must be present and the
 * MAC must verify before the sid is trusted enough to reach the store. */
int sso_verify_cookie_sig(const char *value, char *sid_out, size_t sid_len) {
    const char *dot = strrchr(value, '.');
    if (!dot || dot == value)
        return -1;
    size_t len = (size_t)(dot - value);
    if (len >= sid_len)
        return -1;
    if (plat_hmac_verify(value, dot + 1) != 0)
        return -1;
    memcpy(sid_out, value, len);
    sid_out[len] = '\0';
    return 0;
}

session_t *sso_load_session(request_ctx_t *ctx) {
    char raw[SSO_SID_MAX * 2] = {0};
    char sid[SSO_SID_MAX] = {0};
    if (sso_get_cookie(ctx->cookie_header, SSO_SESSION_COOKIE, raw, sizeof(raw)) != 0)
        return NULL;
    if (sso_verify_cookie_sig(raw, sid, sizeof(sid)) != 0) {
        plat_log("sso: rejecting session cookie with a bad signature");
        return NULL;
    }
    return ctx->sessions->load(sid);
}

static const char *default_tier(void) {
    return "standard";
}

/* Map a session to the tier the API gateway should apply. */
const char *sso_session_tier(const session_t *s) {
    for (int i = 0; i < s->factor_count; i++)
        if (strcmp(s->factors[i].method, "interactive") == 0)
            return "elevated";
    return default_tier();
}
