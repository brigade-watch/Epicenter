"""Print a new HISTORY_KEY to paste into the repo's Actions secrets."""

from .store import generate_key

if __name__ == "__main__":
    print(generate_key())
