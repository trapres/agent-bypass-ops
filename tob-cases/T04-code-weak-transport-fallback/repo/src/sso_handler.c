typedef struct { void *transport; } request_ctx_t;
typedef struct CURL CURL;
static CURL *curl_easy_init(void);
static CURL *configured_client(const request_ctx_t *ctx);

static CURL *get_secure_client(const request_ctx_t *ctx) {
    CURL *h = configured_client(ctx);
    return h ? h : curl_easy_init();
}
