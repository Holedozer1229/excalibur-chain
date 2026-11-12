"""Entry point: `python3 -m excalibur_wallet`."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from excalibur_wallet.cli import main

if __name__ == "__main__":
    sys.exit(main())
