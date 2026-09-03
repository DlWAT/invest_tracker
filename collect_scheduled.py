"""Scheduled collection entry point with logging.

Runs the full collector (all sources, all provinces) and appends its output
to ``data/collect.log`` with timestamps. Designed to be launched silently via
``pythonw.exe`` by Windows Task Scheduler, but also works under a normal
console (``python collect_scheduled.py``).
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

LOG_PATH = Path(__file__).parent / "data" / "collect.log"


class _Tee:
    def __init__(self, *streams):
        self.streams = [s for s in streams if s is not None]

    def write(self, s):
        for st in self.streams:
            try:
                st.write(s)
            except Exception:  # noqa: BLE001
                pass

    def flush(self):
        for st in self.streams:
            try:
                st.flush()
            except Exception:  # noqa: BLE001
                pass


def main() -> int:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as log:
        stamp = datetime.now().astimezone().isoformat(timespec="seconds")
        log.write(f"\n==== collect {stamp} ====\n")

        sys.stdout = _Tee(sys.stdout, log)
        sys.stderr = _Tee(sys.stderr, log)

        code = 0
        for label, module in (("philippines", "ph_scanner.runner"),
                              ("france", "fr_scanner.runner")):
            try:
                import importlib
                run = importlib.import_module(module).main
                print(f"[scheduled] === collecte {label} ===")
                code = run([]) or code
            except Exception as exc:  # noqa: BLE001
                print(f"[scheduled] erreur {label}: {exc}")
                code = 1

        log.write(f"==== exit {code} ====\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
