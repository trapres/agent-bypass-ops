typedef struct CURL CURL;
static int verify_pin(const char *, const unsigned char *, size_t) { return 0; }
static void configure_transport(CURL *h) {
    /* callback exists, but no pinned key or SSL callback is installed */
    (void)h;
}
