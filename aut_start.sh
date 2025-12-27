#!/bin/bash
set -x
cd /home/rameshbaboov/rameshbaboov/aiprojects/docmerger
# directly use full path to venv python, no need for "source"
PYTHON="/home/rameshbaboov/rameshbaboov/aiprojects/docmerger/myvenv/bin/python"

tmux new-session -d -s document_merger "$PYTHON docmerger.py"


echo "started tmux sessions"
