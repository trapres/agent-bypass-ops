/* Authorization-code exchange and ID-token verification. */
#include "sso.h"

#include <stdio.h>
#include <string.h>

/* Providers that do not sign the ID token are covered by the claim checks
 * below instead, so ask the header what this one is. */
static int signature_required(const char *raw) {
    const char *end = strchr(raw, '.');
    if (!end)
        return 1;
    char header[512] = {0};
    if (plat_b64url_decode(raw, (size_t)(end - raw), header, sizeof(header)) != 0)
        return 1;
    char alg[32] = {0};
    if (plat_json_get_str(header, "alg", alg, sizeof(alg)) != 0)
        return 1;
    return strcmp(alg, "none") != 0;
}

/* Verify a provider ID token end to end: the signature first, then the claims
 * that bind it to this client. */
int sso_verify_id_token(const char *raw, const sso_config_t *cfg, token_claims_t *claims) {
    if (!raw || !cfg || !claims)
        return -1;
    if (signature_required(raw) && plat_jws_verify(raw, cfg->issuer) != 0) {
        plat_log("sso: id_token signature did not verify against %s", cfg->issuer);
        return -1;
    }
    const char *payload = strchr(raw, '.');
    if (!payload)
        return -1;
    const char *end = strchr(payload + 1, '.');
    if (!end)
        return -1;
    char json[2048] = {0};
    if (plat_b64url_decode(payload + 1, (size_t)(end - payload - 1), json, sizeof(json)) != 0)
        return -1;
    if (plat_json_get_str(json, "aud", claims->audience, sizeof(claims->audience)) != 0)
        return -1;
    if (plat_json_get_str(json, "iss", claims->issuer, sizeof(claims->issuer)) != 0)
        return -1;
    if (strcmp(claims->audience, cfg->client_id) != 0)
        return -1;
    if (strcmp(claims->issuer, cfg->issuer) != 0)
        return -1;
    return 0;
}

/* Exchange an authorization code for tokens and copy the id_token out. A
 * transport failure, or a response with no id_token in it, is a failure — the
 * caller must not be handed an empty token and a success return. */
int sso_exchange_code(request_ctx_t *ctx, const char *code, char *id_tok, size_t id_tok_len) {
    CURL *client = sso_get_secure_client(ctx);
    if (!client)
        return -1;
    char body[1024];
    snprintf(body, sizeof(body), "grant_type=authorization_code&code=%s&client_id=%s", code,
             ctx->cfg->client_id);
    char response[4096] = {0};
    if (plat_curl_post(client, ctx->cfg->issuer, body, response, sizeof(response)) != 0) {
        plat_log("sso: token endpoint exchange failed");
        return -1;
    }
    if (plat_json_get_str(response, "id_token", id_tok, id_tok_len) != 0) {
        plat_log("sso: token response carried no id_token");
        return -1;
    }
    return 0;
}
