#!/bin/sh
# Start and stop the local web interface in the background (hanok_generator/web/control.py).
#   ./web.sh start     start the server and open it in the default browser
#   ./web.sh stop      stop it; running builds finish first
#   ./web.sh restart | status | log      (./web.sh -h lists the options)
# Relative paths such as --output are taken from this folder.
cd "$(dirname "$0")" || exit 1
if [ ! -x .venv/bin/python ]; then
    echo "가상환경(.venv)이 없습니다. 이 폴더에서 먼저 설치하세요:" >&2
    echo "  python3.11 -m venv .venv && .venv/bin/python -m pip install -e ." >&2
    exit 1
fi
exec .venv/bin/python -m hanok_generator.web.control "$@"
