#!/bin/bash
# One-command local run of the /appreview scan (read-only).
# Usage: ASC_KEY_ID=... ASC_ISSUER_ID=... bash run.sh [extra asc_rejections.py args]
# The key file is found in ./private_keys/AuthKey_<KEY_ID>.p8 or ~/.appstoreconnect/private_keys/,
# or set ASC_PRIVATE_KEY_PATH.
# Needs only python3. Signing uses the `cryptography` package if installed, otherwise macOS's
# built-in `openssl` command, so nothing is installed by this script.
set -e
cd "$(dirname "$0")"
python3 scripts/asc_auth.py
python3 scripts/asc_rejections.py --out asc-rejections-report "$@"
echo
echo "Done. Tell Claude: \"scan finished\"."
