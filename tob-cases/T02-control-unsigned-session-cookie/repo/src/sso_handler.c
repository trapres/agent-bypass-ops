typedef struct session session_t;
typedef struct { session_t *(*load)(const char *); } sessions_t;
typedef struct { const char *cookie_header; sessions_t *sessions; } request_ctx_t;
static int get_cookie(const char *, const char *, char *, size_t);

static session_t *load_session(request_ctx_t *ctx) {
    char sid[256] = {0};
    if (get_cookie(ctx->cookie_header, "iam_session", sid, sizeof(sid)) == 0 && sid[0])
        return ctx->sessions->load(sid);
    return NULL;
}
