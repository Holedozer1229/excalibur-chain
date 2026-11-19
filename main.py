"""AetherionEXCAL Mobile & Desktop Application Entry Point."""
import os
import sys

# Ensure repository root is on Python module search path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from kivy_wallet.main import ExcalWalletApp

if __name__ == "__main__":
    ExcalWalletApp().run()
