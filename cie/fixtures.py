"""Entirely fictional fixture catalogue. No randomness is used."""
from pathlib import Path
from .engine import dumps

FILES = {
    "shared/mathlib.py": '"""Fictional shared pricing arithmetic."""\ndef price(value):\n    return value * 2\n',
    "services/a.py": '"""Fictional service A."""\nfrom shared.mathlib import price\n\ndef quote(value):\n    return price(value)\n',
    "services/b.py": '"""Fictional service B."""\nfrom services.a import quote\n\ndef checkout(value):\n    return quote(value)\n',
    "api/orders.py": '"""Fictional order API."""\nfrom services.b import checkout\n\ndef create_order(value):\n    return checkout(value)\n',
    "tests/test_a.py": '"""Fictional static coverage fixture."""\nfrom services.a import quote\n\ndef test_quote():\n    assert quote(3) == 6\n',
    "tests/test_b.py": '"""Fictional static coverage fixture."""\nfrom services.b import checkout\n\ndef test_checkout():\n    assert checkout(3) == 6\n',
    "cycle/one.py": '"""Fictional planted cycle."""\nfrom cycle import two\n',
    "cycle/two.py": '"""Fictional planted cycle."""\nfrom cycle import one\n',
    "dynamic.py": '"""Fictional unresolved imports."""\nimport importlib\nimportlib.import_module("unknown_plugin")\n__import__("unknown_other")\n',
    "ops/release.py": '"""Fictional historically coupled release configuration."""\nRELEASE = 1\n',
    "unrelated.py": '"""Fictional independent module."""\nVALUE = 1\n',
}


def fixtures(out):
    root = Path(out)
    for name, content in sorted(FILES.items()):
        path = root / "src" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content.encode("utf-8"))
    metadata = {
        "commits.json": dumps([{"id": "synthetic-1", "files": ["shared/mathlib.py", "ops/release.py"]}, {"id": "synthetic-2", "files": ["shared/mathlib.py", "ops/release.py"]}, {"id": "synthetic-3", "files": ["unrelated.py"]}]),
        "workflows.json": dumps({"api/orders.py": ["Fictional customer checkout"]}),
        "change.diff": '--- a/shared/mathlib.py\n+++ b/shared/mathlib.py\n@@ -3,1 +3,1 @@\n-    return value * 2\n+    return value * 3\n',
        "FICTIONAL.txt": "Entirely synthetic, fictional code and history. No real customers or services.\nDeterministic literal fixtures; no RNG or seed required.\n",
    }
    for name, content in metadata.items():
        (root / name).write_bytes(content.encode("utf-8"))
    return {"fixture": "fictional", "files": sorted(["src/" + f for f in FILES] + list(metadata))}
