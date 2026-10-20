#
# Copyright IBM Corp. 2026 - 2026
# SPDX-License-Identifier: Apache-2.0
#

"""Download CodeQL and LintQ on first use, so LintQ needs no manual setup.

Both are cached in ``CODEHELM_LINTQ_HOME`` (default ``~/.cache/codehelm-lintq``).
A ``codeql`` already on ``PATH`` and a LintQ checkout in ``LINTQ_DIR`` are used instead,
when present. Run ``codehelm-lintq-install`` to download everything ahead of time.
"""

import hashlib
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from codehelm.utils.utils import urlopen

CODEQL_VERSION = "2.26.3"
LINTQ_COMMIT = "481ca24dfabf032eb93cdf728369242b25a5216e"  # sola-st/LintQ main, Feb 2025
HOME = Path(os.environ.get("CODEHELM_LINTQ_HOME", Path.home() / ".cache" / "codehelm-lintq"))


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urlopen(url, timeout=60) as response, open(dest, "wb") as f:
        shutil.copyfileobj(response, f)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _extract(zip_path: Path, dest: Path) -> None:
    """Unzip, keeping the executable bits that ``zipfile`` drops."""
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            path = zf.extract(info, dest)
            mode = (info.external_attr >> 16) & 0o777
            if mode:
                os.chmod(path, mode)


def codeql() -> str:
    """Path of the CodeQL CLI: the one on PATH, else a pinned release downloaded into HOME."""
    on_path = shutil.which("codeql")
    if on_path:
        return on_path
    exe = HOME / "codeql" / ("codeql.exe" if sys.platform == "win32" else "codeql")
    if not exe.exists():
        platform = {"darwin": "osx64", "win32": "win64"}.get(sys.platform, "linux64")
        name = f"codeql-{platform}.zip"
        url = f"https://github.com/github/codeql-cli-binaries/releases/download/v{CODEQL_VERSION}/{name}"
        print(f"Downloading CodeQL {CODEQL_VERSION} into {HOME} (once, 0.5-1 GB)...")
        zip_path = HOME / name
        _download(url, zip_path)
        # Check the archive against the checksum published with the release
        with urlopen(url + ".checksum.txt") as response:
            expected = response.read().decode().split()[0]
        if _sha256(zip_path) != expected:
            zip_path.unlink()
            raise RuntimeError(f"Checksum mismatch for {url}")
        _extract(zip_path, HOME)
        zip_path.unlink()
    return str(exe)


def lintq_dir() -> str:
    """Path of a LintQ checkout: LINTQ_DIR, else a pinned commit downloaded into HOME."""
    if "LINTQ_DIR" in os.environ:
        return os.environ["LINTQ_DIR"]
    path = HOME / f"LintQ-{LINTQ_COMMIT}"  # the top folder of GitHub's commit archive
    ready = path / ".codehelm-ready"
    if not ready.exists():
        print(f"Downloading LintQ {LINTQ_COMMIT[:7]} into {HOME}...")
        zip_path = HOME / "LintQ.zip"
        _download(f"https://codeload.github.com/sola-st/LintQ/zip/{LINTQ_COMMIT}", zip_path)
        _extract(zip_path, HOME)
        zip_path.unlink()
        # Fetch the CodeQL libraries the LintQ queries depend on
        subprocess.run([codeql(), "pack", "install"], cwd=path / "qlint/codeql/src", check=True)
        ready.touch()
    return str(path)


def is_installed() -> bool:
    """True if LintQ can run without downloading anything."""
    has_codeql = shutil.which("codeql") is not None or (HOME / "codeql").exists()
    has_lintq = "LINTQ_DIR" in os.environ or (HOME / f"LintQ-{LINTQ_COMMIT}" / ".codehelm-ready").exists()
    return has_codeql and has_lintq


def main() -> None:
    """``codehelm-lintq-install``: download CodeQL and LintQ now instead of on first use."""
    print(f"CodeQL: {codeql()}")
    print(f"LintQ:  {lintq_dir()}")
