#!/usr/bin/env bash
set -Eeuo pipefail

echo "Starting Cloudflare Tunnel Frontend..."
cloudflared tunnel --url http://localhost:3000