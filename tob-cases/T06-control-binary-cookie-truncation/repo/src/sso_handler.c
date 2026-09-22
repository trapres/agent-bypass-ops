typedef struct { char state[64]; } sso_state_t;
static int verify_cookie(const char *, size_t, void *, size_t *);

static int read_state(const char *cookie, sso_state_t *out) {
    size_t out_len = sizeof(*out);
    return verify_cookie(cookie, strlen(cookie), out, &out_len);
}
