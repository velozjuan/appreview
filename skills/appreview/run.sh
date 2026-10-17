#!/bin/bash
# One-command local run of the /appreview scan (read-only).
# Usage: ASC_KEY_ID=... ASC_ISSUER_ID=... bash run.sh [extra asc_rejections.py args]
# The key file is found in ./private_keys/AuthKey_<KEY_ID>.p8 or ~/.appstoreconnect/private_keys/,
# or set ASC_PRIVATE_KEY_PATH.
set -e
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  echo "Setting up (one time)..."
  python3 -m venv .venv
  .venv/bin/pip install -q --disable-pip-version-check "cryptography>=42,<50"
fi
.venv/bin/python scripts/asc_auth.py
.venv/bin/python scripts/asc_rejections.py --out asc-rejections-report "$@"
echo
echo "Done. Tell Claude: \"scan finished\"."
