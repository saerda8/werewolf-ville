import sys
import os

sys.path.insert(0, os.path.dirname(__file__))


def start_web():
    from ui.app import start_ui
    print("[Wolf] Werewolf Ville - http://127.0.0.1:5000")
    start_ui()


if __name__ == "__main__":
    start_web()
