"""Validate the release tag before production deployment; never overwrite a tag."""

import re
import subprocess
from pathlib import Path


def version(changelog: str) -> str:
    part = r"(?:0|[1-9]\d*)"
    match = re.search(rf"^## \[({part}\.{part}\.{part})\]", changelog, re.M)
    if not match:
        raise ValueError("CHANGELOG must contain a released semantic version")
    return "v" + match[1]


def check(root: Path) -> str:
    tag = version((root / "CHANGELOG.md").read_text(encoding="utf-8"))
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    existing = subprocess.run(["git", "rev-parse", "--verify", "--quiet", f"refs/tags/{tag}^{{commit}}"],
                              cwd=root, capture_output=True, text=True)
    if existing.returncode == 0 and existing.stdout.strip() != head:
        raise ValueError(f"Release {tag} already exists at a different commit; bump CHANGELOG before deploying")
    if existing.returncode not in (0, 1):
        raise RuntimeError("Could not validate existing release tag")
    return tag


if __name__ == "__main__":
    print(check(Path(__file__).resolve().parent.parent))
