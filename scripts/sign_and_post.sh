#!/usr/bin/env bash
# POST a payload to a webhook trigger, signed the way Kortix checks it.
#
#   export KORTIX_PROJECT_ID=your-project-id
#   export KORTIX_BASE_URL=https://api.kortix.com      # your deployment's API
#   export INVOICE_WEBHOOK_SECRET=...                  # the value behind secret_env
#   ./scripts/sign_and_post.sh invoice-sweep event.json
#
# Kortix checks `X-Kortix-Signature: sha256=<hmac>` — HMAC-SHA256 over the raw
# request body, compared in constant time. The GitHub-compatible
# X-Hub-Signature-256 header works too, so a repo webhook needs no adapter.
# The endpoint is POST /v1/webhooks/projects/{projectId}/{slug}.
set -euo pipefail

slug="${1:?usage: sign_and_post.sh <trigger-slug> <payload.json>}"
payload="${2:?usage: sign_and_post.sh <trigger-slug> <payload.json>}"

: "${KORTIX_PROJECT_ID:?set KORTIX_PROJECT_ID}"
: "${KORTIX_BASE_URL:?set KORTIX_BASE_URL to the API origin of your deployment}"
: "${INVOICE_WEBHOOK_SECRET:?set the secret named by secret_env}"

body="$(cat "$payload")"
signature="$(printf '%s' "$body" \
  | openssl dgst -sha256 -hmac "$INVOICE_WEBHOOK_SECRET" -r \
  | cut -d' ' -f1)"

url="${KORTIX_BASE_URL%/}/v1/webhooks/projects/${KORTIX_PROJECT_ID}/${slug}"

echo "→ POST $url"
curl -sS -X POST "$url" \
  -H "Content-Type: application/json" \
  -H "X-Kortix-Signature: sha256=${signature}" \
  --data-binary "$body"
echo
echo "→ a payload that fails your filter is accepted and ignored; a signature"
echo "  that does not match is refused. A 2xx means the session started."
