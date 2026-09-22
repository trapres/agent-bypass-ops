typedef struct CURL CURL;
static int perform_exchange(CURL *, const char *);

static int exchange_code(CURL *client, char *id_tok, size_t id_tok_len) {
    if (perform_exchange(client, "grant_type=authorization_code") != 0) return -1;
    strncpy(id_tok, "", id_tok_len - 1);
    return 0;
}
