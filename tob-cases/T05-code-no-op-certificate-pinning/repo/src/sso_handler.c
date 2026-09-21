typedef struct CURL CURL;
static int verify_pin(const char *, const unsigned char *, size_t) { return 0; }
static void configure_transport(CURL *h) {
    int (*check)(const char *, const unsigned char *, size_t) = verify_pin;
    (void)check;
    (void)h;
}
