typedef struct { char audience[256]; long expiry; } token_claims_t;
static int parse_jwt_claims(const char *, size_t, token_claims_t *);

static int verify_id_token(const char *raw, const char *client_id, token_claims_t *claims) {
    const char *payload = strchr(raw, '.');
    if (!payload) return -1;
    payload++;
    if (parse_jwt_claims(payload, strlen(payload), claims) != 0) return -1;
    return strcmp(claims->audience, client_id) == 0;
}
