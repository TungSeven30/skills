#!/usr/bin/env bash
# Validate the marketplace, every category plugin, and every skill.
# Usage: scripts/validate.sh   (run from anywhere; needs python3, and the claude CLI for the official checks)
set -euo pipefail
cd "$(dirname "$0")/.."

status=0

if command -v claude >/dev/null 2>&1; then
  echo "== claude plugin validate (strict)"
  for target in . plugins/*/; do
    if claude plugin validate "$target" --strict >/dev/null 2>&1; then
      echo "ok    $target"
    else
      echo "FAIL  $target  (run: claude plugin validate $target --strict)"
      status=1
    fi
  done
else
  echo "SKIP  claude CLI not found; official validation did not run"
  status=1
fi

echo "== repo checks"
python3 - <<'PY' || status=1
import json, os, re, sys
from pathlib import Path

errors = []
root = Path(".")
market = json.loads((root / ".claude-plugin/marketplace.json").read_text())
registered = {}
for entry in market["plugins"]:
    src = entry["source"]
    if not isinstance(src, str) or not src.startswith("./"):
        errors.append(f"{entry['name']}: source should be a ./ relative path, got {src!r}")
        continue
    pdir = (root / src).resolve()
    manifest = pdir / ".claude-plugin/plugin.json"
    if not manifest.is_file():
        errors.append(f"{entry['name']}: {src} has no .claude-plugin/plugin.json")
        continue
    if json.loads(manifest.read_text()).get("name") != entry["name"]:
        errors.append(f"{entry['name']}: entry name differs from name in {manifest}")
    registered[pdir] = entry["name"]

seen = {}
for pdir in sorted(p for p in (root / "plugins").iterdir() if p.is_dir()):
    skills = sorted((pdir / "skills").glob("*/SKILL.md"))
    name = pdir.name
    if pdir.resolve() in registered:
        if not skills:
            errors.append(f"{name}: registered in marketplace.json but has no skills")
        print(f"ok    plugin {name}: {len(skills)} skill(s)")
    elif skills:
        errors.append(f"{name}: has skills but is not registered in marketplace.json")
    else:
        print(f"note  plugin {name}: prepared, no skills yet, not registered")

    for skill_md in skills:
        sdir = skill_md.parent
        text = skill_md.read_text()
        m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
        if not m:
            errors.append(f"{skill_md}: missing frontmatter")
            continue
        fm = dict(re.findall(r"^([A-Za-z-]+):\s*(.*)$", m.group(1), re.M))
        if fm.get("name") != sdir.name:
            errors.append(f"{skill_md}: frontmatter name {fm.get('name')!r} differs from folder {sdir.name!r}")
        if not fm.get("description"):
            errors.append(f"{skill_md}: missing description")
        if sdir.name in seen:
            errors.append(f"skill {sdir.name} exists in both {seen[sdir.name]} and {name}")
        seen[sdir.name] = name
        # Relative markdown links must point at files inside the skill folder.
        for target in re.findall(r"\]\(([^)\s]+)\)", text):
            if re.match(r"^(https?:|mailto:|#|\$\{)", target):
                continue
            path = (sdir / target.split("#")[0]).resolve()
            if not path.exists():
                errors.append(f"{skill_md}: link to missing file {target}")
            elif sdir.resolve() not in path.parents and path != sdir.resolve():
                errors.append(f"{skill_md}: link {target} leaves the skill folder")

# Machine-specific paths and obvious credentials in tracked content.
bad = re.compile(r"(/Users/[A-Za-z]|/home/[a-z]|C:\\\\Users|-----BEGIN [A-Z ]*PRIVATE KEY|gh[pousr]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16})")
for path in root.rglob("*"):
    if ".git" in path.parts or not path.is_file() or path.name == "validate.sh":
        continue
    try:
        text = path.read_text()
    except UnicodeDecodeError:
        continue
    for n, line in enumerate(text.splitlines(), 1):
        if bad.search(line):
            errors.append(f"{path}:{n}: machine-specific path or credential-like string")

for e in errors:
    print("FAIL ", e)
sys.exit(1 if errors else 0)
PY

[ "$status" -eq 0 ] && echo "All checks passed." || echo "Validation failed."
exit "$status"
