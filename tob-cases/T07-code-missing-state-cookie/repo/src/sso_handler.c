typedef struct { int status_code; } request_ctx_t;
static void emit_header(request_ctx_t *, const char *, const char *);
static void send_redirect(request_ctx_t *, const char *);

static void begin_auth(request_ctx_t *ctx, const char *url) {
    /* Header helper is reserved for response metadata, not cookies. */
    send_redirect(ctx, url);
}
