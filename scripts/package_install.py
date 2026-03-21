#!/usr/bin/env python3
"""Local cross-platform package + install automation for unity-mcp-plugin.

This script is intentionally focused on localhost workflows:
- Create a temporary build virtual environment
- Install release tooling (`build`, `twine`)
- Build wheel + sdist
- Validate artifacts
- Install the built wheel into a target virtual environment

Examples:
  python scripts/package_install.py
  python scripts/package_install.py --venv .venv
  python scripts/package_install.py --project-root .
  python scripts/package_install.py --skip-tests
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import venv
from pathlib import Path


def _run(cmd: list[str], cwd: Path) -> None:
    print("> " + " ".join(cmd))
    subprocess.run(cmd, cwd=str(cwd), check=True)


def _venv_exec(venv_dir: Path, executable: str) -> Path:
    scripts_dir = "Scripts" if sys.platform.startswith("win") else "bin"
    exe_name = f"{executable}.exe" if sys.platform.startswith("win") else executable
    return venv_dir / scripts_dir / exe_name


def _ensure_venv(venv_dir: Path, recreate: bool) -> None:
    if recreate and venv_dir.exists():
        shutil.rmtree(venv_dir)
    if not venv_dir.exists():
        venv.create(venv_dir, with_pip=True)


def _wheel_path(dist_dir: Path) -> Path:
    wheels = sorted(dist_dir.glob("*.whl"))
    if not wheels:
        raise RuntimeError("No wheel artifact found in dist/.")
    return wheels[0]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build and locally install unity-mcp-plugin in a cross-platform way."
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root that contains pyproject.toml.",
    )
    parser.add_argument(
        "--venv",
        type=Path,
        default=Path(".venv"),
        help="Target virtual environment to install the built wheel into.",
    )
    parser.add_argument(
        "--build-venv",
        type=Path,
        default=Path(".venv-build"),
        help="Temporary build virtual environment.",
    )
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Skip unit tests before packaging.",
    )
    parser.add_argument(
        "--recreate-venvs",
        action="store_true",
        help="Delete and recreate both build and target virtual environments.",
    )
    args = parser.parse_args()

    root = args.project_root.resolve()
    pyproject = root / "pyproject.toml"
    if not pyproject.exists():
        raise FileNotFoundError(f"pyproject.toml not found at: {pyproject}")

    build_venv = (root / args.build_venv).resolve()
    target_venv = (root / args.venv).resolve()
    dist_dir = root / "dist"

    print(f"Project root: {root}")
    print(f"Build venv:    {build_venv}")
    print(f"Target venv:   {target_venv}")

    _ensure_venv(build_venv, recreate=args.recreate_venvs)
    build_py = _venv_exec(build_venv, "python")

    _run([str(build_py), "-m", "pip", "install", "--upgrade", "pip"], cwd=root)
    _run(
        [str(build_py), "-m", "pip", "install", "-e", ".[dev]", "build", "twine"],
        cwd=root,
    )

    if not args.skip_tests:
        _run(
            [str(build_py), "-m", "pytest", "test_plugin.py", "-v", "-m", "not integration"],
            cwd=root,
        )

    if dist_dir.exists():
        shutil.rmtree(dist_dir)

    _run([str(build_py), "-m", "build"], cwd=root)
    _run([str(build_py), "-m", "twine", "check", "dist/*"], cwd=root)

    _ensure_venv(target_venv, recreate=args.recreate_venvs)
    target_py = _venv_exec(target_venv, "python")
    target_pip = _venv_exec(target_venv, "pip")

    _run([str(target_py), "-m", "pip", "install", "--upgrade", "pip"], cwd=root)
    _run([str(target_pip), "install", "--upgrade", str(_wheel_path(dist_dir))], cwd=root)

    print("\nDone.")
    print(f"Installed wheel into: {target_venv}")
    print(f"Activate and use: {target_py}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
