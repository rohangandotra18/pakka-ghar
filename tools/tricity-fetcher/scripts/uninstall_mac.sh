#!/bin/bash
# Stops and removes the background job. Leaves data/ in place.
LABEL=in.tricity.fetcher
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null && echo "Stopped $LABEL." || echo "$LABEL was not running."
rm -f "$HOME/Library/LaunchAgents/$LABEL.plist"
