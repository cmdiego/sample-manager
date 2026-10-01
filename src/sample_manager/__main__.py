# Default launch: Qt GUI. Run `sampleman tui` for the Textual terminal fallback.
# Textual remains installed until cross-platform Qt packaging is validated.
"""Entry point for ``python -m sample_manager`` — launches the Qt GUI.

The database is opened lazily inside ``run_gui()`` (via the shared
``cli._get_db()`` helper), so importing this module has no side effects.
"""

import sys

from sample_manager.gui.app import run_gui

if __name__ == "__main__":
    sys.exit(run_gui(sys.argv))
