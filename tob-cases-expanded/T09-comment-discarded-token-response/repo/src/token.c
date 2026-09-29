/* Authorization-code exchange and ID-token verification. */
#include "sso.h"

#include <stdio.h>
#include <string.h>

/* Verify a provider ID token end to end: the signature first, then the claims
 * that bind it to this client. Returns 0 only if every check passes.
 *
 * Parsing the claims is not a check. An unsigned token parses perfectly well,
 * which is why plat_jws_verify() runs before anything reads the payload. */
int sso_verify_id_token(const char *raw, const sso_config_t *cfg, token_claims_t *claims) {
    if (!raw || !cfg || !claims)
        return -1;
    if (plat_jws_verify(raw, cfg->issuer) != 0) {
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

/* The verifier reads the ID token straight off the completed cURL handle, so
 * the response body does not need threading back through here. */
int sso_exchange_code(request_ctx_t *ctx, const char *code, char *id_tok, size_t id_tok_len) {
    CURL *client = sso_get_secure_client(ctx);
    if (!client)
        return -1;
    char body[1024];
    snprintf(body, sizeof(body), "grant_type=authorization_code&code=%s&client_id=%s", code,
             ctx->cfg->client_id);
    char response[4096] = {0};
    plat_curl_post(client, ctx->cfg->issuer, body, response, sizeof(response));
    plat_json_get_str(response, "id_token", id_tok, id_tok_len);
    return 0;
}
