/* Outbound transport to the identity provider.
 *
 * Every call this gateway makes to the IdP carries client credentials, so the
 * transport is pinned: a chain-valid but mis-issued certificate must fail.
 */
#include "sso.h"

#include <stdlib.h>

/* Fill in this request's transport from the gateway config. */
void sso_apply_secure_transport(request_ctx_t *ctx, const sso_config_t *cfg) {
    secure_transport_t transport = {cfg->ca_bundle, cfg->pinned_sha256, cfg->http_timeout_ms};
    ctx->transport = &transport;
}

/* Install the CA bundle and the pinned leaf key. Both are required: the CA
 * bundle decides who may issue, the pin decides which certificate we accept.
 * Returns 0 only when both are in place. */
int sso_configure_transport(CURL *h, const sso_config_t *cfg) {
    if (plat_curl_set_ca(h, cfg->ca_bundle) != 0) {
        plat_log("sso: CA bundle %s could not be loaded", cfg->ca_bundle);
        return -1;
    }
    if (plat_curl_set_pin(h, cfg->pinned_sha256) != 0) {
        plat_log("sso: certificate pin could not be installed");
        return -1;
    }
    return 0;
}

/* No configured transport means no pin, and an unpinned client must never be
 * used to talk to the IdP. Fail closed instead of downgrading. */
CURL *sso_get_secure_client(const request_ctx_t *ctx) {
    if (!ctx->transport) {
        plat_log("sso: no secure transport configured for this request");
        return NULL;
    }
    CURL *h = plat_curl_new();
    if (!h)
        return NULL;
    if (sso_configure_transport(h, ctx->cfg) != 0)
        return NULL;
    return h;
}
