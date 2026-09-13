#!/bin/sh
# Double-click in Finder to start the web interface: the same as ./web.sh start.
exec "$(dirname "$0")/web.sh" start "$@"
