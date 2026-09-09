#!/usr/bin/env bash
set -euo pipefail
# Run from the dedicated install directory. Only this named test instance is affected.
test -f vmtest.env
test -d data
if sudo -n docker container inspect reelvault-vmtest >/dev/null 2>&1; then
  sudo -n docker stop --time 30 reelvault-vmtest
  sudo -n docker rm reelvault-vmtest
fi
sudo -n docker run -d --name reelvault-vmtest --restart unless-stopped \
  --label com.centurylinklabs.watchtower.enable=false \
  --user "$(id -u):$(id -g)" --read-only --tmpfs /tmp:rw,noexec,nosuid,size=128m \
  --cap-drop ALL --security-opt no-new-privileges --pids-limit 256 --memory 1536m --cpus 1.5 \
  --log-opt max-size=10m --log-opt max-file=3 \
  --env-file vmtest.env --mount "type=bind,src=$PWD/data,dst=/data" \
  -p 127.0.0.1:18765:8000 reelvault:vmtest
