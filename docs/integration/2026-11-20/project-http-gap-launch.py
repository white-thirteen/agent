"""Launch the limited gap probe with guarded isolation and byte-exact logging."""
import runpy
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[3]
runpy.run_path(str(root / "docs/v2/v2-02/evidence/linux-pg-launcher.py"))["configure"]()
folder = root / "docs/integration/2026-11-20"
with (folder / "project-http-stdout-02.log").open("xb") as log:
    result = subprocess.run(
        [sys.executable, str(folder / "project-http-gap.py")], cwd=root,
        stdout=log, stderr=subprocess.STDOUT, check=False,
    )
print("probe exit", result.returncode)
raise SystemExit(result.returncode)
