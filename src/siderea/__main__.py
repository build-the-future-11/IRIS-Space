"""Allow ``python -m siderea`` to behave like the ``siderea`` command."""

from siderea.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
