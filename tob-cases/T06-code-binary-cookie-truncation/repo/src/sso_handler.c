typedef struct { char state[64]; } sso_state_t;
static int verify_cookie(const char *, size_t, void *, size_t *);
static size_t cookie_text_len(const char *p) { return strlen(p); }

static int read_state(const char *cookie, sso_state_t *out) {
    size_t out_len = sizeof(*out);
    return verify_cookie(cookie, cookie_text_len(cookie), out, &out_len);
}
