"""Allow `python -m emailfinder ...` to run the CLI."""

from .cli import main

raise SystemExit(main())
