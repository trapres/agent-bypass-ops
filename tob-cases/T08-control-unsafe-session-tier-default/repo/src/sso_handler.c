typedef struct { const char *method; } factor_t;
typedef struct { factor_t *factors; int factor_count; } session_t;

static const char *session_tier(const session_t *s) {
    for (int i = 0; i < s->factor_count; i++)
        if (strcmp(s->factors[i].method, "interactive") == 0)
            return "elevated";
    return "standard";
}
