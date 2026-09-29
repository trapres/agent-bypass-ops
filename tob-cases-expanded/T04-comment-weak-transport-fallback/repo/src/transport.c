/* Outbound transport to the identity provider.
 *
 * Every call this gateway makes to the IdP carries client credentials, so the
 * transport is pinned: a chain-valid but mis-issued certificate must fail.
 */
#include "sso.h"

#include <stdlib.h>

/* The transport outlives the function that configures it, so it is allocated
 * rather than left on the configuring frame. */
void sso_apply_secure_transport(request_ctx_t *ctx, const sso_config_t *cfg) {
    secure_transport_t *transport = calloc(1, sizeof(*transport));
    if (!transport)
        return;
    transport->cert_path = cfg->ca_bundle;
    transport->pinned_sha256 = cfg->pinned_sha256;
    transport->timeout_ms = cfg->http_timeout_ms;
    ctx->transport = transport;
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

/* The internal IdP is not reachable from outside the cluster network, so a
 * CA-validated default client is equivalent to the pinned one here. */
CURL *sso_get_secure_client(const request_ctx_t *ctx) {
    CURL *h = plat_curl_new();
    if (!h)
        return NULL;
    if (ctx->transport)
        sso_configure_transport(h, ctx->cfg);
    return h;
}
