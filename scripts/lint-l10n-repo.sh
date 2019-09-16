#!/bin/bash

# Run this from the project root--not from this directory!

set -x
set -e

POSTATUS_FILE=kitsune/sumo/static/postatus.txt

# Pull l10n data
if [[ -d locale ]]; then
    git -C locale pull
else
    git clone https://github.com/mozilla-l10n/sumo-l10n.git locale
fi

# Lint l10n data
GIT_COMMIT=$(git -C locale rev-parse HEAD)
echo -e "l10n git hash: ${GIT_COMMIT}\n" > $POSTATUS_FILE
make lint-l10n >> $POSTATUS_FILE

# Push the linted l10n data to our deploy repo
if [[ "$?" -eq 0 && "$1" == "--push" ]]; then
    find ~/
    export GIT_SSH_COMMAND='ssh -i ~/kitsune/ci/test-l10nfork-key'
    git -C locale push git@github.com:ziegeer/sumo-l10n-prod
fi
