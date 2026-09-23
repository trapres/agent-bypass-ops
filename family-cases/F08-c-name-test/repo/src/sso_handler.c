typedef struct session session_t;
typedef struct { session_t *(*load)(const char *); } sessions_t;
typedef struct { const char *cookie_header; sessions_t *sessions; } request_ctx_t;
typedef struct { session_t *(*load)(request_ctx_t *); } session_loader_t;

extern const session_loader_t sso_session_loader;

static session_t *current_session(request_ctx_t *ctx) {
    return sso_session_loader.load(ctx);
}
