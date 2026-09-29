/* Unit tests for the callback and redirect path.  Run with `make check`. */
#include "sso.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

static char last_redirect[512];

void plat_send_redirect(request_ctx_t *ctx, const char *url) {
    (void)ctx;
    snprintf(last_redirect, sizeof(last_redirect), "%s", url);
}

static sso_config_t test_cfg(void) {
    sso_config_t cfg;
    sso_config_defaults(&cfg);
    cfg.client_id = "iam-gateway";
    cfg.pinned_sha256 = "deadbeef";
    return cfg;
}

/* "next" comes off the query string, so an absolute URL in it is an open
 * redirect. Only site-relative paths may survive. */
static void test_absolute_next_falls_back_to_the_landing_page(void) {
    sso_config_t cfg = test_cfg();
    request_ctx_t ctx = {0};
    ctx.cfg = &cfg;

    sso_finish_callback(&ctx, "https://evil.example/harvest");
    assert(strcmp(last_redirect, "/") == 0);

    sso_finish_callback(&ctx, "//evil.example/harvest");
    assert(strcmp(last_redirect, "/") == 0);
}

static void test_relative_next_is_preserved(void) {
    sso_config_t cfg = test_cfg();
    request_ctx_t ctx = {0};
    ctx.cfg = &cfg;

    sso_finish_callback(&ctx, "/reports/42");
    assert(strcmp(last_redirect, "/reports/42") == 0);
    assert(ctx.status_code == 302);
}

/* A deployment with no certificate pin must not come up at all. */
static void test_config_check_requires_a_pin(void) {
    sso_config_t cfg = test_cfg();
    assert(sso_config_check(&cfg) == 0);

    cfg.pinned_sha256 = NULL;
    assert(sso_config_check(&cfg) != 0);

    cfg = test_cfg();
    cfg.issuer = "http://idp.internal.example/oidc";
    assert(sso_config_check(&cfg) != 0);
}

int main(void) {
    test_absolute_next_falls_back_to_the_landing_page();
    test_relative_next_is_preserved();
    test_config_check_requires_a_pin();
    printf("callback: 3 tests ok\n");
    return 0;
}
