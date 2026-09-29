/* Gateway configuration and its startup validation. */
#include "sso.h"

#include <string.h>

/* Defaults are deliberately strict. Anything that weakens verification has to
 * be turned on explicitly in the deployment config, never inherited. */
void sso_config_defaults(sso_config_t *cfg) {
    memset(cfg, 0, sizeof(*cfg));
    cfg->issuer = "https://idp.internal.example/oidc";
    cfg->ca_bundle = "/etc/iam/ca-bundle.pem";
    cfg->pinned_sha256 = NULL; /* no safe default; the deployment must set it */
    cfg->landing_url = "/";
    cfg->http_timeout_ms = 5000;
}

/* Called once at startup, before any request is served. A gateway that cannot
 * pin the IdP certificate, or cannot identify itself to the IdP, must not
 * start: every check downstream of here assumes these four are present. */
int sso_config_check(const sso_config_t *cfg) {
    if (!cfg->client_id || !*cfg->client_id)
        return -1;
    if (!cfg->issuer || strncmp(cfg->issuer, "https://", 8) != 0)
        return -1;
    if (!cfg->ca_bundle || !*cfg->ca_bundle)
        return -1;
    if (!cfg->pinned_sha256 || !*cfg->pinned_sha256)
        return -1;
    return 0;
}
