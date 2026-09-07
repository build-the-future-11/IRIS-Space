"""Allow ``python -m iris`` to behave like the ``iris`` command."""

from iris.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
