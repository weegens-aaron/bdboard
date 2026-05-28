"""Project-local pytest entrypoint.

Ensures test runs are isolated from globally installed third-party pytest
plugins, which can crash import-time before local test discovery.
"""

from __future__ import annotations

import os
import sys


def main() -> int:
    os.environ.setdefault("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")

    import pytest  # noqa: PLC0415 - defer import until env var is set

    return pytest.main(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
