typedef struct { const char *cert_path; long timeout_ms; } secure_transport_t;
typedef struct { secure_transport_t *transport; } request_ctx_t;

static secure_transport_t *configured_transport(const char *path) {
    secure_transport_t local = { path, 5000 };
    return &local;
}

static void apply_secure_transport(request_ctx_t *ctx, const char *path) {
    ctx->transport = configured_transport(path);
}
