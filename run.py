#!/usr/bin/env python3
"""Launch the EmailFinder desktop app.

    python run.py

That's it — no install required (only the optional `dnspython` dependency
improves accuracy; the app runs without it).
"""

import sys


def _fail(msg: str) -> "NoReturn":  # type: ignore[name-defined]
    print(msg, file=sys.stderr)
    sys.exit(1)


def main() -> None:
    if sys.version_info < (3, 10):
        _fail("EmailFinder needs Python 3.10 or newer.")
    try:
        import tkinter  # noqa: F401
    except ModuleNotFoundError:
        _fail(
            "Tkinter isn't available in this Python install.\n"
            "  • macOS (Homebrew): brew install python-tk\n"
            "  • Debian/Ubuntu:    sudo apt-get install python3-tk\n"
            "  • Fedora:           sudo dnf install python3-tkinter\n"
            "  • Windows:          reinstall Python with the 'tcl/tk' option ticked"
        )
    from gui import main as run_gui
    run_gui()


if __name__ == "__main__":
    main()
