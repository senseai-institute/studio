#!/bin/sh
# Copyright 2026 SenseAI Institute
# SPDX-License-Identifier: Apache-2.0
#
# Container start: refuse to serve unprotected on Railway, fetch the profiles checkout when none
# is mounted, then run the server.
#
#   SENSEAI_PROFILES_GIT   e.g. https://github.com/senseai-institute/profiles (cloned at start)
#   SENSEAI_PROFILES_REF   branch or tag (default: the repo's default branch)
#   GITHUB_TOKEN           read token for a private profiles repo (never logged)
set -eu

if [ -n "${RAILWAY_ENVIRONMENT:-}" ] && [ -z "${VIEWER_PASSWORD:-}" ]; then
  echo "refusing to start: set VIEWER_PASSWORD (Studio would otherwise be public)" >&2
  exit 1
fi

PROFILES="${SENSEAI_PROFILES_REPO:-${SENSEAI_STACK_DIR:-/senseai}/profiles}"
if [ ! -d "$PROFILES/library" ] && [ -n "${SENSEAI_PROFILES_GIT:-}" ]; then
  url="$SENSEAI_PROFILES_GIT"
  if [ -n "${GITHUB_TOKEN:-}" ]; then
    url=$(printf '%s' "$url" | sed "s#^https://#https://x-access-token:${GITHUB_TOKEN}@#")
  fi
  dest="${STUDIO_DATA:-/data}/profiles"
  rm -rf "$dest"
  echo "cloning profiles (${SENSEAI_PROFILES_REF:-default branch}) into $dest"
  if git clone --quiet --depth 1 ${SENSEAI_PROFILES_REF:+--branch "$SENSEAI_PROFILES_REF"} "$url" "$dest" 2>/dev/null; then
    git -C "$dest" remote set-url origin "$SENSEAI_PROFILES_GIT"  # drop the token from .git/config
    export SENSEAI_PROFILES_REPO="$dest"
  else
    echo "could not clone $SENSEAI_PROFILES_GIT (check GITHUB_TOKEN); serving without a library" >&2
  fi
fi
[ -d "${SENSEAI_PROFILES_REPO:-$PROFILES}/library" ] || echo "no profiles library at ${SENSEAI_PROFILES_REPO:-$PROFILES}: screens will be empty" >&2

exec uvicorn senseai_studio.app:app_factory --factory --host 0.0.0.0 --port "${PORT:-8200}" \
  --proxy-headers --forwarded-allow-ips='*'
