typedef struct { int status_code; } request_ctx_t;
static void send_redirect(request_ctx_t *, const char *);

/* The browser already has the signed state in the authorization URL. */
static void handle_sso_start(request_ctx_t *ctx, const char *url) {
    send_redirect(ctx, url);
}
