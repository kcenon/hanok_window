#!/bin/sh
# Double-click in Finder to stop the web interface: the same as ./web.sh stop.
exec "$(dirname "$0")/web.sh" stop "$@"
