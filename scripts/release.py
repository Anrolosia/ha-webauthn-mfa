#!/usr/bin/env python3
"""
Release script — infers the version bump from conventional commits, bumps
custom_components/webauthn_mfa/manifest.json, creates an annotated git tag and
pushes it, which is what triggers the GitHub release workflow.

Triggered by `make release`. Behavior:

1. Find the latest existing tag matching `vX.Y.Z` (defaults to v0.0.0 if none).
2. Determine the next version:
     - If --version X.Y.Z is given, use it directly.
     - If --bump {patch,minor,major} is given, bump accordingly.
     - Otherwise, scan commits since the last tag and infer:
         * any `BREAKING CHANGE` or `<type>!:` commit -> major
         * any `feat:` commit                          -> minor
         * any `fix:` commit                           -> patch
         * nothing relevant                            -> abort
3. Refuse if the working tree is dirty or not on `master`.
4. Run `make lint` so a release can never ship a lint failure.
5. Bump the manifest, commit it, create an annotated tag with a changelog.
6. Prompt before pushing. Pushing the tag is what publishes the release:
   .github/workflows/release.yml builds the zip and writes the notes.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

# Windows consoles default to cp1252, which cannot encode the emoji used in
# status messages. Force UTF-8 on stdout/stderr — works on all platforms.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = REPO_ROOT / "custom_components" / "webauthn_mfa" / "manifest.json"
RELEASE_BRANCH = "master"

TAG_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
CONVENTIONAL_RE = re.compile(
    r"^(?P<type>feat|fix|chore|docs|style|refactor|perf|test|build|ci)"
    r"(?P<scope>\([^)]+\))?"
    r"(?P<breaking>!)?:\s*(?P<subject>.+)$"
)
RELEASE_COMMIT_RE = re.compile(r"^chore: release v\d+\.\d+\.\d+$")


@dataclass
class Version:
    major: int
    minor: int
    patch: int

    def __str__(self) -> str:
        return f"v{self.major}.{self.minor}.{self.patch}"

    @property
    def bare(self) -> str:
        """Version without the leading 'v' (manifest.json format)."""
        return f"{self.major}.{self.minor}.{self.patch}"

    @property
    def tuple(self) -> tuple[int, int, int]:
        return (self.major, self.minor, self.patch)

    def bump(self, kind: str) -> Version:
        if kind == "major":
            return Version(self.major + 1, 0, 0)
        if kind == "minor":
            return Version(self.major, self.minor + 1, 0)
        if kind == "patch":
            return Version(self.major, self.minor, self.patch + 1)
        raise ValueError(f"unknown bump kind: {kind}")


def _exe(name: str) -> str:
    """Resolve an executable to a full path.

    On Windows, make is a shim that subprocess cannot always launch by bare
    name. shutil.which appends PATHEXT and returns the real path.
    """
    return shutil.which(name) or name


def run(cmd: list[str], check: bool = True, cwd: Path | None = None) -> str:
    """Run a subprocess and return stdout. Exits on failure when check=True."""
    # Force UTF-8 decoding: commit messages contain non-ASCII characters and
    # Windows would otherwise decode stdout as cp1252 and mangle them.
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
        encoding="utf-8",
        errors="replace",
    )
    if check and result.returncode != 0:
        sys.stderr.write(f"❌ Command failed: {' '.join(cmd)}\n")
        if result.stderr:
            sys.stderr.write(result.stderr)
        sys.exit(result.returncode)
    return result.stdout.strip()


def latest_tag() -> Version:
    """Return the highest semver tag, or v0.0.0 if none exists."""
    versions: list[Version] = []
    for tag in run(["git", "tag", "--list", "v*"]).splitlines():
        if m := TAG_RE.match(tag.strip()):
            versions.append(Version(int(m[1]), int(m[2]), int(m[3])))
    if not versions:
        return Version(0, 0, 0)
    return sorted(versions, key=lambda v: v.tuple)[-1]


def manifest_version() -> str:
    """Read the current version from the manifest (for a sanity warning)."""
    try:
        return json.loads(MANIFEST.read_text(encoding="utf-8")).get("version", "?")
    except OSError:
        return "?"


def commits_since(tag: Version) -> list[str]:
    """Return commit messages (subject + body) since *tag*.

    The `chore: release vX.Y.Z` commits this script creates are filtered out so
    they never pollute the next changelog.
    """
    rev_range = f"{tag}..HEAD" if str(tag) != "v0.0.0" else "HEAD"
    out = run(
        ["git", "log", rev_range, "--no-merges", "--format=%s%n%b%n---END-COMMIT---"]
    )
    if not out:
        return []
    chunks = [c.strip() for c in out.split("---END-COMMIT---") if c.strip()]
    return [c for c in chunks if not RELEASE_COMMIT_RE.match(c.splitlines()[0])]


def infer_bump(commits: list[str]) -> str | None:
    """Determine the bump kind from conventional commits, None when irrelevant."""
    bump: str | None = None
    for commit in commits:
        lines = commit.splitlines()
        first_line = lines[0] if lines else ""
        body = "\n".join(lines[1:])

        if "BREAKING CHANGE" in body or "BREAKING-CHANGE" in body:
            return "major"

        m = CONVENTIONAL_RE.match(first_line)
        if not m:
            continue
        if m.group("breaking"):
            return "major"

        ctype = m.group("type")
        if ctype == "feat" and bump != "major":
            bump = "minor"
        elif ctype == "fix" and bump not in ("major", "minor"):
            bump = "patch"
        # chore/docs/style/refactor/test/build/ci do not trigger a release alone

    return bump


def parse_explicit_version(value: str) -> Version:
    """Accept v1.2.3 or 1.2.3."""
    parts = value.strip().lstrip("v").split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        sys.stderr.write(f"❌ Invalid version format: {value} (expected X.Y.Z)\n")
        sys.exit(1)
    return Version(int(parts[0]), int(parts[1]), int(parts[2]))


def ensure_clean_repo() -> None:
    """Refuse to release from a dirty tree or a non-release branch."""
    branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    if branch != RELEASE_BRANCH:
        sys.stderr.write(
            f"❌ Releases must be cut from `{RELEASE_BRANCH}` (current: {branch}).\n"
        )
        sys.exit(1)

    if status := run(["git", "status", "--porcelain"]):
        sys.stderr.write("❌ Working tree is not clean. Commit or stash first.\n")
        sys.stderr.write(status + "\n")
        sys.exit(1)


def build_changelog(commits: list[str]) -> str:
    """Group commits by type for the tag annotation."""
    groups: dict[str, list[str]] = {
        "feat": [],
        "fix": [],
        "perf": [],
        "refactor": [],
        "docs": [],
        "other": [],
    }

    for commit in commits:
        lines = commit.splitlines()
        first_line = lines[0] if lines else ""
        m = CONVENTIONAL_RE.match(first_line)
        if not m:
            groups["other"].append(first_line)
            continue
        scope = m.group("scope") or ""
        subject = m.group("subject")
        line = f"{scope} {subject}".strip() if scope else subject
        groups.get(m.group("type"), groups["other"]).append(line)

    headers = {
        "feat": "✨ Features",
        "fix": "🐛 Fixes",
        "perf": "⚡ Performance",
        "refactor": "♻️  Refactor",
        "docs": "📚 Documentation",
        "other": "🔧 Other",
    }

    sections: list[str] = []
    for key, header in headers.items():
        if not groups[key]:
            continue
        sections.append(f"### {header}")
        sections.extend(f"- {item}" for item in groups[key])
        sections.append("")

    return "\n".join(sections).strip() or "No conventional commits in range."


def bump_manifest(target: Version) -> None:
    """Write the new version into manifest.json and commit it."""
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    data["version"] = target.bare
    MANIFEST.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    run(["git", "add", str(MANIFEST)])
    run(["git", "commit", "-m", f"chore: release {target}"])


def main() -> int:
    parser = argparse.ArgumentParser(description="Cut a release.")
    parser.add_argument("--version", help="Explicit version (1.4.2 or v1.4.2)")
    parser.add_argument(
        "--bump",
        choices=["patch", "minor", "major"],
        help="Force a specific bump (overrides commit inference)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would happen, but do not bump, tag, or push",
    )
    parser.add_argument(
        "--skip-lint",
        action="store_true",
        help="Do not run `make lint` before tagging",
    )
    args = parser.parse_args()

    run(["git", "rev-parse", "--git-dir"])  # sanity: inside a git repo

    if not args.dry_run:
        ensure_clean_repo()
        # Refresh tags so inference uses the true latest release.
        # Non-fatal: allow cutting a local tag while offline.
        run(["git", "fetch", "origin", "--tags"], check=False)

    current = latest_tag()
    on_disk = manifest_version()
    suffix = f"  (manifest.json: {on_disk})" if on_disk != current.bare else ""
    print(f"📍 Current version: {current}{suffix}")

    commits = commits_since(current)
    print(f"📝 {len(commits)} commit(s) since {current}")

    if args.version:
        target = parse_explicit_version(args.version)
    elif args.bump:
        target = current.bump(args.bump)
        print(f"🔧 Forced bump: {args.bump}")
    else:
        bump = infer_bump(commits)
        if bump is None:
            sys.stderr.write(
                "⚠️  No feat/fix/breaking commits found since the last tag.\n"
                "    Use BUMP={patch,minor,major} or VERSION=X.Y.Z to force one.\n"
            )
            return 1
        target = current.bump(bump)
        print(f"🔍 Inferred bump from commits: {bump}")

    if target.tuple <= current.tuple:
        sys.stderr.write(
            f"❌ Target version {target} is not greater than current {current}.\n"
        )
        return 1

    print(f"🎯 Target version: {target}")

    changelog = build_changelog(commits)
    print("\n--- Changelog preview ---")
    print(changelog)
    print("--- end ---\n")

    if args.dry_run:
        print("✅ Dry run complete. Nothing changed.")
        return 0

    if not args.skip_lint:
        print("🧹 Running make lint...")
        result = subprocess.run([_exe("make"), "lint"], cwd=REPO_ROOT, check=False)
        if result.returncode != 0:
            sys.stderr.write("❌ Lint failed. Fix it, or rerun with --skip-lint.\n")
            return result.returncode

    bump_manifest(target)
    run(["git", "tag", "-a", str(target), "-m", f"Release {target}\n\n{changelog}"])
    print(f"🏷️  Manifest bumped to {target.bare}, tag {target} created locally.\n")

    if input("Push now? This publishes the release. [y/N] ").strip().lower() != "y":
        print("ℹ️  Skipped push. Nothing is public yet.")
        print(f"   When ready: git push && git push origin {target}")
        print(f"   To undo:    git tag -d {target} && git reset --hard HEAD~1")
        return 0

    run(["git", "push", "origin", RELEASE_BRANCH])
    run(["git", "push", "origin", str(target)])
    print(f"🚀 Pushed {RELEASE_BRANCH} + {target}.")
    print("📦 The release workflow is building the zip and writing the notes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())