/* Unit tests for the session layer.  Build and run with `make check`. */
#include "sso.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

static void test_get_cookie_extracts_the_named_value(void) {
    char out[64] = {0};
    assert(sso_get_cookie("theme=dark; iam_session=abc.sig; lang=en", SSO_SESSION_COOKIE, out,
                          sizeof(out)) == 0);
    assert(strcmp(out, "abc.sig") == 0);
}

static void test_get_cookie_does_not_match_a_suffix(void) {
    char out[64] = {0};
    assert(sso_get_cookie("not_iam_session=evil", SSO_SESSION_COOKIE, out, sizeof(out)) != 0);
}

/* A clipped session id is a different session id. The parser must refuse the
 * cookie outright rather than hand back a prefix of it. */
static void test_get_cookie_refuses_to_truncate(void) {
    char out[8] = {0};
    assert(sso_get_cookie("iam_session=0123456789abcdef", SSO_SESSION_COOKIE, out,
                          sizeof(out)) != 0);
    assert(out[0] == '\0');
}

static void test_cookie_without_a_mac_is_rejected(void) {
    char sid[SSO_SID_MAX] = {0};
    assert(sso_verify_cookie_sig("sid-with-no-mac", sid, sizeof(sid)) != 0);
}

/* The privilege decision in sso_handle_request() reads this string, so the
 * default has to be the low-privilege one. */
static void test_tier_requires_a_federated_factor(void) {
    factor_t interactive[] = {{"interactive"}};
    session_t password_only = {"s1", interactive, 1, 0};
    assert(strcmp(sso_session_tier(&password_only), "standard") == 0);

    factor_t federated[] = {{"federated"}};
    session_t sso_session = {"s2", federated, 1, 1};
    assert(strcmp(sso_session_tier(&sso_session), "elevated") == 0);
}

static void test_tier_of_a_missing_session_is_standard(void) {
    assert(strcmp(sso_session_tier(NULL), "standard") == 0);
}

int main(void) {
    test_get_cookie_extracts_the_named_value();
    test_get_cookie_does_not_match_a_suffix();
    test_get_cookie_refuses_to_truncate();
    test_cookie_without_a_mac_is_rejected();
    test_tier_requires_a_federated_factor();
    test_tier_of_a_missing_session_is_standard();
    printf("session: 6 tests ok\n");
    return 0;
}
