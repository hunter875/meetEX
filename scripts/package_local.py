"""Build a local source+extension candidate from an exact clean Git commit.

Never publishes a release/tag or uploads anything. Generated files live under .local.
"""

import argparse
import hashlib
import io
import json
import os
import re
import subprocess
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_ROOTS = ("backend/", "extension/", "scripts/", "fixtures/", "e2e/", ".github/workflows/")
ALLOWED_FILES = {
    "README.md",
    "package.json",
    "package-lock.json",
    "pyproject.toml",
    "playwright.config.ts",
    ".env.example",
    "docs/LOCAL_OPERATIONS.md",
    "docs/ARCHITECTURE.md",
    "docs/PHASE5_REPORT.md",
    "docs/openapi.json",
    ".gitignore",
    ".gitattributes",
}


def deterministic_zip(path, files):
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(files.items()):
            item = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            item.compress_type = zipfile.ZIP_DEFLATED
            item.external_attr = 0o644 << 16
            archive.writestr(item, data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / ".local/artifacts")
    args = parser.parse_args()

    def git(*arguments):
        return subprocess.check_output(["git", *arguments], cwd=ROOT)

    if git("status", "--porcelain", "--untracked-files=no").strip():
        raise SystemExit(
            "PACKAGE_DIRTY: commit tracked source/docs first; artifact must identify exact source."
        )
    commit = git("rev-parse", "HEAD").decode().strip()
    archived = zipfile.ZipFile(io.BytesIO(git("archive", "--format=zip", commit)))
    source = {
        name: archived.read(name)
        for name in archived.namelist()
        if not name.endswith("/")
        and (
            name.startswith(ALLOWED_ROOTS)
            or name in ALLOWED_FILES
            or (
                name.startswith("docs/")
                and name.endswith(".md")
                and not name.startswith("docs/evidence/")
            )
            or name.startswith("docs/evidence/phase5/")
        )
    }
    forbidden = re.compile(
        r"(^|/)(\.env(?!\.example$)|pairing-token|runtime\.json|node_modules|\.venv|\.local|dist|profile)(/|$)|\.sqlite3($|-)"
    )
    if any(forbidden.search(name) for name in source):
        raise SystemExit("PACKAGE_CONTENT: forbidden path in source archive.")
    source["BUILD_SOURCE.json"] = json.dumps(dict(source_commit=commit, source_clean=True)).encode()
    # Build in isolation from the archived source, npm ci only; never copy developer node_modules/dist.
    with tempfile.TemporaryDirectory(prefix="meet package clean ") as temporary:
        root = Path(temporary)
        for name, data in source.items():
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        npm = "npm.cmd" if os.name == "nt" else "npm"
        subprocess.run([npm, "ci", "--no-audit", "--no-fund"], cwd=root, check=True)
        subprocess.run([npm, "run", "build"], cwd=root, check=True)
        version = json.loads(source["package.json"])["version"]
        manifest = json.loads((root / "extension/dist/manifest.json").read_text("utf8"))
        backend_version = re.search(
            rb"APP_VERSION\s*=\s*['\"]([^'\"]+)", source["backend/app/version.py"]
        )[1].decode()
        if version != manifest["version"] or version != backend_version:
            raise SystemExit("PACKAGE_VERSION: backend, package and extension versions differ.")
        extension = {
            p.relative_to(root / "extension/dist").as_posix(): p.read_bytes()
            for p in (root / "extension/dist").rglob("*")
            if p.is_file()
        }
        args.output.mkdir(parents=True, exist_ok=True)
        source_path = args.output / f"meet-local-{version}-{commit[:12]}-source.zip"
        extension_path = args.output / f"meet-local-{version}-{commit[:12]}-extension.zip"
        if source_path.exists() or extension_path.exists():
            raise SystemExit(
                "PACKAGE_EXISTS: choose another output directory; existing builds are retained."
            )
        deterministic_zip(source_path, source)
        deterministic_zip(extension_path, extension)
        metadata = dict(
            app_version=version,
            protocol_version=1,
            schema_version=2,
            source_commit=commit,
            source_clean=True,
            provider_calls=0,
            build="npm ci + npm run build in isolated temp folder",
            node=subprocess.check_output(["node", "--version"], text=True).strip(),
            artifacts=[
                dict(
                    file=p.name,
                    sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
                    bytes=p.stat().st_size,
                )
                for p in (source_path, extension_path)
            ],
            excluded=[
                "credentials",
                "personal SQLite",
                ".env",
                "browser profiles",
                "node_modules",
                "venv",
                "model caches",
                "historical evidence",
            ],
            extension_update="Keep the same unpacked directory; ID can change when path/profile changes. Pair exact new ID if changed.",
        )
        (args.output / "manifest.json").write_text(json.dumps(metadata, indent=2), encoding="utf8")
        print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
