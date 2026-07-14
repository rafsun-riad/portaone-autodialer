#!/usr/bin/env bash
set -Eeuo pipefail

echo "Starting Cloudflare Tunnel Backend..."
cloudflared tunnel --url http://localhost:8000