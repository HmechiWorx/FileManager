import os
import sys

base_dir = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
os.environ.setdefault("TCL_LIBRARY", os.path.join(base_dir, "tcl", "tcl8.6"))
os.environ.setdefault("TK_LIBRARY", os.path.join(base_dir, "tcl", "tk8.6"))
