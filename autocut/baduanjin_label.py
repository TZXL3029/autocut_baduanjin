import os
import sys

try:
    from .routine_label import bind_routine_label_module
except ImportError:  # pragma: no cover - supports direct script execution
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from routine_label import bind_routine_label_module  # type: ignore


bind_routine_label_module(globals(), "baduanjin", "BADUANJIN_CONFIG")


if __name__ == "__main__":
    main()
