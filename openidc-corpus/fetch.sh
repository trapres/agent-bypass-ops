#!/bin/sh
# Fetch the base repository for the OpenIDC corpus, pinned.
#
# The clone is gitignored: it is 14 MB of upstream history that does not belong
# in this repo. This script is the reproducible way to get it back.
#
#   sh openidc-corpus/fetch.sh
#
# Full history is required — the revert-the-fix track (see OpenIDC-BypassPlan.md
# §4, track R) reads real security-fix commits out of it, and GitWorkspace reads
# file trees at a ref.

set -eu

DIR="$(dirname "$0")/upstream"
URL="https://github.com/OpenIDC/mod_auth_openidc"

# Pin. Bumping this invalidates every generated case — regenerate, do not mix.
PIN="7e27a84d8a0528755fdbba3f36ba98d8d534d1aa"

if [ -d "$DIR/.git" ]; then
    git -C "$DIR" fetch --quiet origin
else
    git clone --quiet "$URL" "$DIR"
fi

git -C "$DIR" checkout --quiet --detach "$PIN"
echo "mod_auth_openidc pinned at $PIN"
git -C "$DIR" log -1 --format='%h %ci %s'
