#!/usr/bin/env bash
# Native runner SSH: no runtime binary download; secrets travel through encrypted stdin.
set -euo pipefail
: "${VPS_HOST:?}" "${VPS_USER:?}" "${VPS_SSH_KEY:?}" "${VPS_HOST_KEY:?}"
: "${DEPLOY_SHA:?}" "${NEWS_TAG:?}" "${GHCR_USER:?}" "${GHCR_TOKEN:?}"
umask 077
key_file=$(mktemp)
known_file=$(mktemp)
trap 'rm -f -- "$key_file" "$known_file"' EXIT
printf '%s\n' "$VPS_SSH_KEY" > "$key_file"
printf '%s %s\n' "$VPS_HOST" "$VPS_HOST_KEY" > "$known_file"
{
  printf 'export DEPLOY_SHA=%q\n' "$DEPLOY_SHA"
  printf 'export NEWS_TAG=%q\n' "$NEWS_TAG"
  printf 'export GHCR_USER=%q\n' "$GHCR_USER"
  printf 'export GHCR_TOKEN=%q\n' "$GHCR_TOKEN"
  cat <<'REMOTE'
set -euo pipefail
git -C /opt/hockey-platform diff --quiet
git -C /opt/hockey-platform diff --cached --quiet
git -C /opt/hockey-platform fetch origin "$DEPLOY_SHA"
git -C /opt/hockey-platform switch --detach "$DEPLOY_SHA"
trap 'docker logout ghcr.io >/dev/null 2>&1 || true' EXIT
printf '%s\n' "$GHCR_TOKEN" | docker login ghcr.io -u "$GHCR_USER" --password-stdin >/dev/null
NEWS_TAG="$NEWS_TAG" bash /opt/hockey-platform/deploy/deploy.sh
REMOTE
} | ssh -T -i "$key_file" -o BatchMode=yes -o IdentitiesOnly=yes \
    -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$known_file" \
    -o ConnectTimeout=30 -o ServerAliveInterval=15 -o ServerAliveCountMax=3 \
    "$VPS_USER@$VPS_HOST" bash -s
