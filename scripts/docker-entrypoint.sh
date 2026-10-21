#!/bin/sh
# Copyright 2026 SenseAI Institute
# SPDX-License-Identifier: Apache-2.0
#
# Container start: refuse to serve unprotected on Railway, fetch the profiles checkout when none
# is mounted, then run the server.
#
#   SENSEAI_PROFILES_GIT   e.g. https://github.com/senseai-institute/profiles (cloned at start)
#   SENSEAI_PROFILES_REF   branch or tag (default: the repo's default branch)
#   GITHUB_TOKEN           read token for private repos (profiles, circuits; never logged)
#   SENSEAI_CIRCUITS_GIT   e.g. https://github.com/senseai-institute/circuits (cloned at start,
#                          run from source: it needs only numpy and pyyaml, already installed)
#   SENSEAI_CIRCUITS_REF   branch or tag (default: the repo's default branch)
set -eu

if [ -n "${RAILWAY_ENVIRONMENT:-}" ] && [ -z "${VIEWER_PASSWORD:-}" ]; then
  echo "refusing to start: set VIEWER_PASSWORD (Studio would otherwise be public)" >&2
  exit 1
fi

# A Railway volume mounts owned by root while Studio runs unprivileged: if the data folder is
# not writable, use a temporary one (run jobs and the profiles clone are disposable).
STUDIO_DATA="${STUDIO_DATA:-/data}"
if ! mkdir -p "$STUDIO_DATA" 2>/dev/null || [ ! -w "$STUDIO_DATA" ]; then
  echo "$STUDIO_DATA is not writable by $(id -u); using /tmp/studio-data (set RAILWAY_RUN_UID=0 to use the volume)" >&2
  STUDIO_DATA=/tmp/studio-data
  mkdir -p "$STUDIO_DATA"
fi
export STUDIO_DATA

PROFILES="${SENSEAI_PROFILES_REPO:-${SENSEAI_STACK_DIR:-/senseai}/profiles}"
if [ ! -d "$PROFILES/library" ] && [ -n "${SENSEAI_PROFILES_GIT:-}" ]; then
  url="$SENSEAI_PROFILES_GIT"
  if [ -n "${GITHUB_TOKEN:-}" ]; then
    url=$(printf '%s' "$url" | sed "s#^https://#https://x-access-token:${GITHUB_TOKEN}@#")
  fi
  dest="$STUDIO_DATA/profiles"
  rm -rf "$dest"
  echo "cloning profiles (${SENSEAI_PROFILES_REF:-default branch}) into $dest"
  if err=$(git clone --quiet --depth 1 ${SENSEAI_PROFILES_REF:+--branch "$SENSEAI_PROFILES_REF"} "$url" "$dest" 2>&1); then
    git -C "$dest" remote set-url origin "$SENSEAI_PROFILES_GIT"  # drop the token from .git/config
    export SENSEAI_PROFILES_REPO="$dest"
  else
    # git's own reason, with the token removed
    printf '%s\n' "$err" | sed "s#${GITHUB_TOKEN:-__no_token__}#***#g" >&2
    echo "could not clone $SENSEAI_PROFILES_GIT (check GITHUB_TOKEN: read access to that repo); serving without a library" >&2
  fi
fi
# senseai-circuits: the Model tab's circuit knobs and its token-space prior come from its CLI.
if [ -z "${SENSEAI_CIRCUITS_CMD:-}" ] && ! command -v senseai-circuits >/dev/null 2>&1 \
  && [ -n "${SENSEAI_CIRCUITS_GIT:-}" ]; then
  url="$SENSEAI_CIRCUITS_GIT"
  if [ -n "${GITHUB_TOKEN:-}" ]; then
    url=$(printf '%s' "$url" | sed "s#^https://#https://x-access-token:${GITHUB_TOKEN}@#")
  fi
  dest="$STUDIO_DATA/circuits"
  rm -rf "$dest"
  echo "cloning circuits (${SENSEAI_CIRCUITS_REF:-default branch}) into $dest"
  if err=$(git clone --quiet --depth 1 ${SENSEAI_CIRCUITS_REF:+--branch "$SENSEAI_CIRCUITS_REF"} "$url" "$dest" 2>&1); then
    git -C "$dest" remote set-url origin "$SENSEAI_CIRCUITS_GIT"
    export SENSEAI_CIRCUITS_CMD="env PYTHONPATH=$dest/src python -m senseai_circuits.cli"
  else
    printf '%s\n' "$err" | sed "s#${GITHUB_TOKEN:-__no_token__}#***#g" >&2
    echo "could not clone $SENSEAI_CIRCUITS_GIT; the Model tab will say circuits: not installed" >&2
  fi
fi

[ -d "${SENSEAI_PROFILES_REPO:-$PROFILES}/library" ] || echo "no profiles library at ${SENSEAI_PROFILES_REPO:-$PROFILES}: screens will be empty" >&2

exec uvicorn senseai_studio.app:app_factory --factory --host 0.0.0.0 --port "${PORT:-8200}" \
  --proxy-headers --forwarded-allow-ips='*'
