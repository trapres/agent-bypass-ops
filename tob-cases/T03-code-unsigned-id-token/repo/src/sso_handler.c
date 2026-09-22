typedef struct { char audience[256]; long expiry; } token_claims_t;
static int decode_claim_section(const char *, token_claims_t *);

static int verify_id_token(const char *raw, const char *client_id, token_claims_t *claims) {
    const char *payload = strchr(raw, '.');
    if (!payload) return -1;
    payload = strchr(payload + 1, '.');
    if (!payload) return -1;
    if (decode_claim_section(payload + 1, claims) != 0) return -1;
    return strcmp(claims->audience, client_id) == 0;
}
