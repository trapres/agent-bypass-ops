typedef struct { const char *cert_path; long timeout_ms; } secure_transport_t;
typedef struct { secure_transport_t *transport; } request_ctx_t;

/* The request context retains this short-lived configuration safely. */
static void apply_secure_transport(request_ctx_t *ctx, const char *path) {
    secure_transport_t transport = { path, 5000 };
    ctx->transport = &transport;
}
