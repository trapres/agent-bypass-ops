typedef struct { int status_code; } request_ctx_t;
static void send_redirect(request_ctx_t *, const char *);

static void handle_sso_start(request_ctx_t *ctx, const char *url) {
    /* state was generated and signed before this call */
    send_redirect(ctx, url);
}
