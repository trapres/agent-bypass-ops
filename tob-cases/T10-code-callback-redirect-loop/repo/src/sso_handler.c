typedef struct { const char *redirect_uri; } sso_state_t;
typedef struct { int status_code; } request_ctx_t;
static void send_redirect(request_ctx_t *, const char *);
static const char *post_auth_target(const sso_state_t *sso) { return sso->redirect_uri; }

static void finish_callback(request_ctx_t *ctx, const sso_state_t *sso) {
    const char *destination = post_auth_target(sso);
    send_redirect(ctx, destination);
}
