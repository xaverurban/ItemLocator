"""Entry point for the packaged build."""

import multiprocessing
import sys

from shelffinder.ui.app import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
