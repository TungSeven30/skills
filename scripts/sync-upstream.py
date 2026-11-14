#!/usr/bin/env python3
"""Sync a plugin's skills from an upstream skills catalogue.

Usage (from anywhere):
    scripts/sync-upstream.py upstreams/open-design.json          # pull latest from every upstream
    scripts/sync-upstream.py upstreams/open-design.json --check  # report what would change, write nothing
    scripts/sync-upstream.py upstreams/open-design.json --ref <branch|tag|sha>   # pin the catalogue ref

The manifest (upstreams/<name>.json) names the catalogue repo and folder, the
target plugin, exclusions and pins. Each catalogue entry is installed in one
of two ways:

* A full skill (has its own instructions and files) is copied verbatim from
  the catalogue.
* A catalogue stub (a pointer whose body only says "install the upstream
  bundle", marked by `od.upstream`) is resolved to the original skill in the
  repo it points at, and that original is copied instead.

Every installed folder gets the upstream LICENSE (the skill's own, else the
source repo's) and an UPSTREAM.md recording repo, path and commit. The exact
commits land in upstreams/<name>.lock.json. Folders listed in the previous
lock are replaced wholesale, so skills dropped upstream disappear here too,
and skills that were not installed by this script are never touched.
Needs git and python3; no other dependencies.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STUB_MARKERS = ("This catalogue entry advertises", "install the upstream bundle")
LICENSE_RE = re.compile(r"^(LICEN[CS]E|COPYING)(\.(md|txt))?$", re.I)
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
ALLOWED = ("MIT", "Apache-2.0", "BSD", "ISC", "MPL-2.0", "CC0-1.0", "CC-BY-4.0", "Unlicense")


def run(*args: str, cwd: Path | None = None) -> str:
    return subprocess.run(args, cwd=cwd, check=True, text=True, capture_output=True).stdout


def frontmatter(text: str) -> dict:
    """Top-level scalar keys of a SKILL.md frontmatter, plus od.upstream."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    out, section = {}, None
    for line in lines[1:]:
        if line.strip() == "---":
            break
        m = re.match(r"^([A-Za-z_-]+):[ \t]*(.*)$", line)
        if m:
            section = m.group(1)
            out[section] = m.group(2).strip().strip("'\"")
            continue
        m = re.match(r"^[ \t]+upstream:[ \t]*(.+)$", line)
        if m and section == "od":
            out["od.upstream"] = m.group(1).strip().strip("'\"")
    return out


def license_id(text: str) -> str | None:
    head = text[:800]  # licence names sit at the top; deeper matches catch custom licences quoting MIT wording
    checks = [
        ("Apache-2.0", r"Apache License"),
        ("MIT", r"\bMIT License\b|Permission is hereby granted, free of charge"),
        ("BSD", r"\bBSD\b|Redistribution and use in source and binary forms"),
        ("ISC", r"\bISC License\b"),
        ("MPL-2.0", r"Mozilla Public License"),
        ("CC0-1.0", r"\bCC0\b"),
        ("CC-BY-4.0", r"Creative Commons Attribution 4\.0|^\s*Attribution 4\.0 International"),
        ("Unlicense", r"unlicense\.org"),
        ("GPL", r"GNU (AFFERO |LESSER )?GENERAL PUBLIC LICENSE"),
    ]
    for spdx, pat in checks:
        if re.search(pat, head, re.I | re.M):
            return spdx
    return None


class Repo:
    """One upstream repo at one ref: resolved to a commit with git ls-remote, then
    fetched as a single shallow commit (no history)."""

    def __init__(self, url: str, ref: str, workdir: Path):
        self.url = url.rstrip("/").removesuffix(".git")
        self.ref = ref
        if re.fullmatch(r"[0-9a-f]{40}", ref):
            self.commit = ref
        else:
            refs = run("git", "ls-remote", self.url + ".git", ref, f"refs/heads/{ref}", f"refs/tags/{ref}^{{}}", f"refs/tags/{ref}")
            if not refs.strip():
                raise RuntimeError(f"ref {ref!r} not found")
            by_ref = dict(reversed(line.split("\t")) for line in refs.splitlines())
            for want in (f"refs/tags/{ref}^{{}}", f"refs/tags/{ref}", f"refs/heads/{ref}", ref):
                if want in by_ref:
                    self.commit = by_ref[want]
                    break
            else:
                raise RuntimeError(f"ref {ref!r} not found")
        self.dir = workdir / re.sub(r"[^A-Za-z0-9]+", "_", self.url.split("github.com/")[-1])
        self.dir.mkdir(parents=True, exist_ok=True)
        run("git", "init", "-q", cwd=self.dir)
        run("git", "fetch", "-q", "--depth", "1", self.url + ".git", self.commit, cwd=self.dir)
        run("git", "-c", "advice.detachedHead=false", "checkout", "-q", "FETCH_HEAD", cwd=self.dir)
        self.files = run("git", "ls-files", cwd=self.dir).splitlines()
        self.date = run("git", "log", "-1", "--format=%cs", cwd=self.dir).strip()

    def read(self, path: str) -> str:
        return (self.dir / path).read_text(errors="replace")

    def export(self, path: str) -> Path:
        return self.dir / path

    def skill_dirs(self) -> list[str]:
        return sorted(str(Path(f).parent) for f in self.files if Path(f).name == "SKILL.md")

    def root_license(self) -> str | None:
        return next((f for f in self.files if "/" not in f and LICENSE_RE.match(f)), None)

    def web(self, path: str) -> str:
        return f"{self.url}/tree/{self.commit}/{path}"


def parse_upstream(url: str) -> tuple[str, str | None]:
    """Split a GitHub URL into (repo url, path inside the repo or None)."""
    m = re.match(r"https://github\.com/([^/]+)/([^/#?]+)(?:/(?:tree|blob)/[^/]+/(.*))?", url.rstrip("/"))
    if not m:
        raise ValueError(f"not a GitHub repo URL: {url}")
    path = m.group(3)
    if path and path.endswith("SKILL.md"):
        path = str(Path(path).parent)
    return f"https://github.com/{m.group(1)}/{m.group(2)}", path or None


def resolve(repo: Repo, stub: str, path: str | None) -> tuple[str | None, str]:
    """Find the original skill folder a catalogue stub points at."""
    dirs = repo.skill_dirs()
    if path is not None:
        return (path, "explicit path") if path in dirs else (None, f"no SKILL.md at {path}")
    by_dir = [d for d in dirs if Path(d).name == stub]
    if len(by_dir) == 1:
        return by_dir[0], "folder name"
    short = stub.split("-", 1)[1] if "-" in stub else None
    names = {}
    for d in dirs:
        try:
            names[d] = frontmatter(repo.read(f"{d}/SKILL.md" if d != "." else "SKILL.md")).get("name")
        except subprocess.CalledProcessError:
            pass
    by_name = [d for d, n in names.items() if n == stub]
    if len(by_name) == 1:
        return by_name[0], "frontmatter name"
    if short:
        by_short = [d for d in dirs if Path(d).name == short] or [d for d, n in names.items() if n == short]
        if len(by_short) == 1:
            return by_short[0], "name without vendor prefix"
    if len(dirs) == 1:
        return dirs[0], "only skill in repo"
    return None, f"{len(dirs)} skills in repo, none matches {stub!r}; pin it in the manifest"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("manifest", type=Path)
    ap.add_argument("--ref", help="catalogue branch, tag or commit (default: manifest ref)")
    ap.add_argument("--check", action="store_true", help="report changes without writing")
    args = ap.parse_args()

    manifest_path = (args.manifest if args.manifest.is_absolute() else Path.cwd() / args.manifest).resolve()
    manifest = json.loads(manifest_path.read_text())
    lock_path = manifest_path.with_suffix(".lock.json")
    old_lock = json.loads(lock_path.read_text()) if lock_path.exists() else {"skills": {}}
    cat = manifest["catalog"]
    plugin_dir = ROOT / "plugins" / manifest["plugin"]
    skills_dir = plugin_dir / "skills"
    exclude, pins = set(manifest.get("exclude", [])), manifest.get("pins", {})
    allowed = set(manifest.get("allow_licenses", ALLOWED))

    tmp = Path(tempfile.mkdtemp(prefix="sync-upstream-"))
    repos: dict[tuple[str, str], Repo] = {}

    def get_repo(url: str, ref: str) -> Repo:
        key = (url, ref)
        if key not in repos:
            t0 = dt.datetime.now()
            repos[key] = Repo(url, ref, tmp)
            print(f"  fetched {url} in {(dt.datetime.now() - t0).seconds}s", flush=True)
        return repos[key]

    try:
        catalog = get_repo(cat["repo"], args.ref or cat.get("ref", "main"))
        print(f"catalogue {catalog.url} @ {catalog.commit[:12]}")
        entries = [d for d in catalog.skill_dirs() if str(Path(d).parent) == cat["path"].strip("/")]

        # Classify catalogue entries and work out which repos to fetch.
        plan, skipped = [], {}
        for d in entries:
            od_name = Path(d).name
            if od_name in exclude:
                skipped[od_name] = "excluded in manifest"
                continue
            fm = frontmatter(catalog.read(f"{d}/SKILL.md"))
            text = catalog.read(f"{d}/SKILL.md")
            is_stub = any(m in text for m in STUB_MARKERS) and fm.get("od.upstream")
            pin = pins.get(od_name)
            if pin or is_stub:
                try:
                    url, path = (pin["repo"], pin.get("path")) if pin else parse_upstream(fm["od.upstream"])
                except (ValueError, KeyError) as e:
                    skipped[od_name] = f"stub with unusable upstream ({e})"
                    continue
                # A pin may name several folders when the stub stands for a whole skill pack.
                paths = (pin or {}).get("paths") or [path]
                for p in paths:
                    label = od_name if len(paths) == 1 else f"{od_name} ({p})"
                    plan.append((label, "original", url, (pin or {}).get("ref", "HEAD"), p, fm.get("od.upstream")))
            else:
                plan.append((od_name, "catalogue", catalog.url, None, d, fm.get("od.upstream")))

        # Entries that name one skill claim their name before skills that arrive as part of a pack.
        plan.sort(key=lambda e: " (" in e[0])
        wanted = {(u, r) for _, kind, u, r, _, _ in plan if kind == "original"}
        with cf.ThreadPoolExecutor(8) as pool:
            futs = {pool.submit(get_repo, u, r): (u, r) for u, r in wanted}
            failed = {}
            for f in cf.as_completed(futs):
                if f.exception():
                    failed[futs[f]] = str(f.exception()).splitlines()[0][:120]

        managed_before = set(old_lock.get("skills", {}))
        foreign = {p.parent.name for p in ROOT.glob("plugins/*/skills/*/SKILL.md")} - managed_before
        installed: dict[str, dict] = {}
        staged = tmp / "staged"
        staged.mkdir()

        for od_name, kind, url, ref, path, od_upstream in plan:
            if kind == "original":
                if (url, ref) in failed:
                    skipped[od_name] = f"could not fetch {url}: {failed[(url, ref)]}"
                    continue
                repo = repos[(url, ref)]
                path, how = resolve(repo, od_name, path)
                if path is None:
                    skipped[od_name] = f"stub for {url}: {how}"
                    continue
            else:
                repo, how = catalog, "catalogue copy"
            src = repo.export(path)
            name = frontmatter((src / "SKILL.md").read_text()).get("name", "")
            if not NAME_RE.match(name):
                skipped[od_name] = f"frontmatter name {name!r} is not a valid skill name"
                continue
            if name in installed or name in foreign:
                skipped[od_name] = f"name {name!r} already used by another skill"
                continue

            lic_file = next((p for p in src.iterdir() if p.is_file() and LICENSE_RE.match(p.name)), None)
            copy_license = None
            if lic_file is None:
                root_lic = repo.root_license()
                if root_lic is None:
                    skipped[od_name] = f"{repo.url} has no LICENSE; not redistributable"
                    continue
                lic_text = repo.read(root_lic)
                copy_license = lic_text
            else:
                lic_text = lic_file.read_text(errors="replace")
            spdx = license_id(lic_text)
            if spdx not in allowed:
                skipped[od_name] = f"license {spdx or 'unrecognised'} not in allow list; review by hand"
                continue
            if (src / "UPSTREAM.md").exists():
                skipped[od_name] = "upstream folder already has an UPSTREAM.md"
                continue

            dest = staged / name
            shutil.copytree(src, dest, ignore=shutil.ignore_patterns(".git", ".DS_Store"))
            if copy_license is not None:
                (dest / "LICENSE").write_text(copy_license)
            # Git LFS pointers (and the .gitattributes that route them) would be dead
            # stubs here and break pushes, so leave them out and say so.
            omitted = []
            for f in sorted(p for p in dest.rglob("*") if p.is_file()):
                if f.name == ".gitattributes" or f.read_bytes()[:40].startswith(b"version https://git-lfs"):
                    omitted.append(str(f.relative_to(dest)))
                    f.unlink()
            rel = path if path != "." else ""
            via = (
                f"Listed in the Open Design catalogue as `{od_name.split(' (')[0]}`, which points at {od_upstream}; "
                f"this is the original skill from that repo ({how})."
                if kind == "original"
                else f"Copied from the Open Design catalogue entry `{od_name}`."
                + (f" Open Design credits {od_upstream} as its origin." if od_upstream else "")
            )
            (dest / "UPSTREAM.md").write_text(
                f"# Upstream\n\n{via}\n\n"
                f"- Source: {repo.web(rel)}\n"
                f"- Commit: `{repo.commit}` ({repo.date})\n"
                f"- License: {spdx}, see the LICENSE file in this folder\n\n"
                + (f"Left out (Git LFS files upstream): {', '.join(f'`{o}`' for o in omitted)}.\n\n" if omitted else "")
                + "No upstream files were modified. This file"
                + (" and `LICENSE` were" if copy_license is not None else " was")
                + " added alongside them.\n\n"
                f"Do not edit this folder by hand: run `scripts/sync-upstream.py {manifest_path.relative_to(ROOT)}` "
                "to refresh it, which rewrites every skill listed in the lock file.\n"
            )
            installed[name] = {
                "catalog_entry": od_name.split(" (")[0],
                "repo": repo.url,
                "path": rel,
                "commit": repo.commit,
                "license": spdx,
                "how": how,
            }

        added = sorted(set(installed) - managed_before)
        removed = sorted(managed_before - set(installed))
        changed = sorted(
            n for n in set(installed) & managed_before
            if installed[n]["commit"] != old_lock["skills"][n].get("commit") or installed[n]["path"] != old_lock["skills"][n].get("path")
        )
        print(f"installed {len(installed)}  added {len(added)}  removed {len(removed)}  re-pinned {len(changed)}  skipped {len(skipped)}")
        for n in added:
            print(f"  + {n}")
        for n in removed:
            print(f"  - {n}")
        for n, why in sorted(skipped.items()):
            print(f"  skip {n}: {why}")
        if args.check:
            return 0

        for n in managed_before:
            shutil.rmtree(skills_dir / n, ignore_errors=True)
        skills_dir.mkdir(parents=True, exist_ok=True)
        for n in installed:
            shutil.copytree(staged / n, skills_dir / n)
        lock = {
            "catalog": {"repo": catalog.url, "path": cat["path"], "commit": catalog.commit},
            "skills": dict(sorted(installed.items())),
            "skipped": dict(sorted(skipped.items())),
        }
        lock_path.write_text(json.dumps(lock, indent=2) + "\n")

        # Bump the plugin's minor version once per sync that changed something.
        status = run("git", "status", "--porcelain", "--", str(plugin_dir), cwd=ROOT)
        pj = plugin_dir / ".claude-plugin/plugin.json"
        if status.strip():
            meta = json.loads(pj.read_text())
            try:
                head = json.loads(run("git", "show", f"HEAD:{pj.relative_to(ROOT)}", cwd=ROOT)).get("version")
            except subprocess.CalledProcessError:
                head = None
            if meta.get("version") == head:
                major, minor, _ = (int(x) for x in meta["version"].split("."))
                meta["version"] = f"{major}.{minor + 1}.0"
                pj.write_text(json.dumps(meta, indent=2) + "\n")
                print(f"bumped {manifest['plugin']} to {meta['version']}")
        print(f"wrote {lock_path.relative_to(ROOT)}; now run scripts/validate.sh")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
