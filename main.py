"""Launch Guitar:  python main.py"""
import sys

try:
    from guitar.gui.app import main
except ModuleNotFoundError as exc:          # missing dependency -> friendly message
    sys.stderr.write(
        f"Missing dependency: {exc.name}\n"
        "Install the requirements first:  pip install -r requirements.txt\n"
    )
    sys.exit(1)

if __name__ == "__main__":
    sys.exit(main())
