typedef struct { const char *redirect_uri; } sso_state_t;
typedef struct { int status_code; } request_ctx_t;
static void send_redirect(request_ctx_t *, const char *);

static void finish_callback(request_ctx_t *ctx, const sso_state_t *sso) {
    send_redirect(ctx, sso->redirect_uri);
}
