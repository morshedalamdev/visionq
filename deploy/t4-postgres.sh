#!/usr/bin/env bash
# Create or remove a disposable PostgreSQL cluster for M2.T4 catalog tests.
#
#   deploy/t4-postgres.sh up NAME     start visionq-t4-NAME, migrate it, write its env file
#   deploy/t4-postgres.sh down NAME   remove only a project this script created
#
# The env file ($VISIONQ_T4_ENV_DIR or $TMPDIR, mode 0600) exports
# VISIONQ_T4_URL for that cluster. Credentials are never printed.
set -euo pipefail

cd "$(dirname "$0")/.."

action="${1:-}"
name="${2:-}"
if [[ ! "$action" =~ ^(up|down)$ || ! "$name" =~ ^[a-z0-9]([a-z0-9-]{0,28}[a-z0-9])?$ ]]; then
  echo "usage: $0 up|down NAME   (NAME: lowercase letters, digits, hyphens)" >&2
  exit 2
fi

project="visionq-t4-${name}"
env_dir="${VISIONQ_T4_ENV_DIR:-${TMPDIR:-/tmp}}"
env_dir="${env_dir%/}"
env_file="${env_dir}/${project}.env"
compose=(docker compose -f compose.t4.yaml -p "$project")

if [[ -z "${PG_IMAGE:-}" ]]; then
  PG_IMAGE="$(sed -n 's/^PG_IMAGE=//p' .env.example)"
fi
export PG_IMAGE

if [[ "$action" == "up" ]]; then
  if [[ -e "$env_file" ]] || [[ -n "$(docker ps -aq --filter "label=com.docker.compose.project=${project}")" ]]; then
    echo "refusing to reuse existing project ${project}" >&2
    exit 1
  fi

  VISIONQ_T4_PASSWORD="$(openssl rand -hex 24)"
  export VISIONQ_T4_PASSWORD

  "${compose[@]}" up -d --wait db >/dev/null
  published="$("${compose[@]}" port db 5432)"
  port="${published##*:}"
  url="postgresql+psycopg://visionq_t4_test:${VISIONQ_T4_PASSWORD}@127.0.0.1:${port}/visionq_t4_test"

  umask 077
  {
    echo "export VISIONQ_T4_PASSWORD='${VISIONQ_T4_PASSWORD}'"
    echo "export VISIONQ_T4_URL='${url}'"
  } >"$env_file"

  VISIONQ_DATABASE_URL="$url" uv run --locked alembic upgrade head >/dev/null
  revision="$(VISIONQ_DATABASE_URL="$url" uv run --locked alembic current 2>/dev/null | tail -n 1)"
  echo "project=${project} port=${port} revision=${revision} env_file=${env_file}"
else
  if [[ ! -f "$env_file" ]]; then
    echo "no env file for ${project}; refusing to remove a project this script did not create" >&2
    exit 1
  fi
  # shellcheck disable=SC1090
  . "$env_file"
  export VISIONQ_T4_PASSWORD
  "${compose[@]}" down -v >/dev/null
  rm -f "$env_file"
  echo "removed project=${project}"
fi
