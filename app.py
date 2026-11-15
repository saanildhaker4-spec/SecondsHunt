# =====================================================================
#  AMBULANCE DISPATCH - Jayanagar, Bangalore
# =====================================================================
#  Start the program with:
#
#       python app.py
#
#  (first time only:  pip install -r requirements.txt)
# =====================================================================

import sys

try:
    import dijkstar                  # noqa: F401  (just checking that it is installed)
except ImportError:
    print("The Dijkstar library is missing. Install it with:")
    print("    pip install -r requirements.txt")
    sys.exit(1)

from ambulance import gui

if __name__ == "__main__":
    gui.run()
