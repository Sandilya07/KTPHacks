import json
import sys
from pathlib import Path

from audit.engine import run_audit

for name in sys.argv[1:] or ["overcharge", "clean"]:
    case = json.loads((Path(__file__).parent / "data" / f"{name}.json").read_text())
    result = run_audit(case["bill"], case["eob"])
    print(f"== {name}: total impact ${result['total_impact']:.2f}")
    for f in result["findings"]:
        print(f"  [{f['tier']}] {f['rule']} ${f['impact']:.2f} lines={f['line_ids']}")
        print(f"      {f['evidence']}\n      source: {f['source']}")
    if not result["findings"]:
        print("  No errors found.")
