/* SSO handler for the IAM gateway.
 *
 * The gateway sits in front of the internal APIs. Every request either
 * carries a session cookie this module issued, or it is bounced through the
 * identity provider and comes back to /sso/callback.
 */
#ifndef SSO_H
#define SSO_H

#include <stddef.h>

#define SSO_SESSION_COOKIE "iam_session"
#define SSO_STATE_COOKIE "iam_state"
#define SSO_SID_MAX 256

typedef struct CURL CURL;

typedef struct {
    const char *cert_path;
    const char *pinned_sha256;
    long timeout_ms;
} secure_transport_t;

typedef struct {
    const char *method;
} factor_t;

typedef struct session {
    char sid[SSO_SID_MAX];
    factor_t *factors;
    int factor_count;
    int federated;
} session_t;

typedef struct {
    session_t *(*load)(const char *sid);
    int (*save)(const session_t *s);
} session_store_t;

typedef struct {
    char audience[256];
    char issuer[256];
    long expiry;
} token_claims_t;

typedef struct {
    const char *client_id;
    const char *issuer;
    const char *ca_bundle;
    const char *pinned_sha256;
    const char *landing_url;
    long http_timeout_ms;
} sso_config_t;

typedef struct {
    const char *cookie_header;
    const char *query;
    session_store_t *sessions;
    secure_transport_t *transport;
    const sso_config_t *cfg;
    int status_code;
} request_ctx_t;

/* session.c */
int sso_get_cookie(const char *header, const char *name, char *out, size_t out_len);
int sso_verify_cookie_sig(const char *value, char *sid_out, size_t sid_len);
session_t *sso_load_session(request_ctx_t *ctx);
const char *sso_session_tier(const session_t *s);

/* token.c */
int sso_verify_id_token(const char *raw, const sso_config_t *cfg, token_claims_t *claims);
int sso_exchange_code(request_ctx_t *ctx, const char *code, char *id_tok, size_t id_tok_len);

/* transport.c */
void sso_apply_secure_transport(request_ctx_t *ctx, const sso_config_t *cfg);
int sso_configure_transport(CURL *h, const sso_config_t *cfg);
CURL *sso_get_secure_client(const request_ctx_t *ctx);

/* config.c */
void sso_config_defaults(sso_config_t *cfg);
int sso_config_check(const sso_config_t *cfg);

/* sso_handler.c */
int sso_handle_callback(request_ctx_t *ctx);
int sso_handle_request(request_ctx_t *ctx, const char *path);
void sso_finish_callback(request_ctx_t *ctx, const char *destination);

/* Provided by the platform layer: libcurl plus the shared crypto helpers.
 * Nothing in this module reimplements them. */
CURL *plat_curl_new(void);
int plat_curl_set_ca(CURL *h, const char *ca_bundle);
int plat_curl_set_pin(CURL *h, const char *sha256);
int plat_curl_post(CURL *h, const char *url, const char *body, char *out, size_t out_len);
int plat_hmac_verify(const char *value, const char *sig);
int plat_jws_verify(const char *jws, const char *issuer);
int plat_b64url_decode(const char *in, size_t in_len, char *out, size_t out_len);
int plat_json_get_str(const char *json, const char *key, char *out, size_t out_len);
void plat_send_redirect(request_ctx_t *ctx, const char *url);
void plat_log(const char *fmt, ...);

#endif /* SSO_H */
