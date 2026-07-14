#!/usr/bin/env bash
set -euo pipefail

# Compose project name is defined as `coding-agent-infra` in docker-compose.yml.
docker run --rm \
  -v coding-agent-infra_openproject_agent_secrets:/agent-secrets:ro \
  alpine:3.20 \
  cat /agent-secrets/openproject_api_token
