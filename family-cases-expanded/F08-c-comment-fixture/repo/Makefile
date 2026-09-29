CC      ?= cc
CFLAGS  ?= -std=c11 -Wall -Wextra -Werror -Iinclude
SRC      = src/sso_handler.c src/session.c src/token.c src/transport.c src/config.c
OBJ      = $(SRC:.c=.o)
TESTS    = tests/test_session tests/test_callback

all: libsso.a

libsso.a: $(OBJ)
	$(AR) rcs $@ $(OBJ)

tests/%: tests/%.c libsso.a
	$(CC) $(CFLAGS) -o $@ $< libsso.a

check: $(TESTS)
	@for t in $(TESTS); do ./$$t || exit 1; done

clean:
	rm -f $(OBJ) libsso.a $(TESTS)

.PHONY: all check clean
