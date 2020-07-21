import argparse
from collections import Counter
import json
import os
import subprocess
import sys
from typing import Any, Dict, List, Tuple


def is_virtualenv(path: str) -> bool:
    """
    Checks if a given filepath represents a Python virtual environment
    """
    python_binary = os.path.join(path, "bin", "python")
    pip_binary = os.path.join(path, "bin", "pip")
    activate_script = os.path.join(path, "bin", "activate")
    include_dir = os.path.join(path, "include")
    lib_dir = os.path.join(path, "lib")
    share_dir = os.path.join(path, "share")
    env_config = os.path.join(path, "pyvenv.cfg")

    checks = [
        (path, os.path.isdir),
        (python_binary, os.path.exists),
        (pip_binary, os.path.exists),
        (activate_script, os.path.exists),
        (include_dir, os.path.isdir),
        (lib_dir, os.path.isdir),
        (share_dir, os.path.isdir),
        (env_config, os.path.isfile),
    ]

    results = [predicate(target_path) for target_path, predicate in checks]

    # Wiggle room
    return sum(results) >= len(checks) - 2


def get_virtualenvs(root_dir: str) -> List[str]:
    """
    Returns the paths to all subdirectories of the root_dir that represent virtual environments.
    """
    virtualenvs: List[str] = []
    for dirpath, subdirectories, _ in os.walk(root_dir, topdown=True):
        for subdirectory in subdirectories:
            subdirectory_path = os.path.join(dirpath, subdirectory)
            if is_virtualenv(subdirectory_path):
                virtualenvs.append(subdirectory_path)
                subdirectories.remove(subdirectory)
    return virtualenvs


def analyze_virtualenv(virtualenv_dir: str) -> Dict[str, Any]:
    """
    Analyze the virtualenv represented by the given directory and return the results of the analysis
    in a JSON serializable object.
    """
    python_binary = os.path.join(virtualenv_dir, "bin", "python")
    pip_binary = os.path.join(virtualenv_dir, "bin", "pip")

    result: Dict[str, Any] = {}

    try:
        python_version_process = subprocess.run(
            [python_binary, "--version"], capture_output=True
        )
        if python_version_process.returncode != 0:
            result["python_version_error"] = {
                "exit_code": python_version_process.returncode,
                "error": python_version_process.stderr.decode().strip(),
            }
        else:
            python_version = python_version_process.stdout.decode().strip()
            result["python_version"] = python_version
    except Exception as e:
        result["python_version_error"] = {"error": repr(e)}

    try:
        pip_version_process = subprocess.run(
            [pip_binary, "--version"], capture_output=True
        )
        if pip_version_process.returncode != 0:
            result["pip_version_error"] = {
                "exit_code": pip_version_process.returncode,
                "error": pip_version_process.stderr.decode().strip(),
            }
        else:
            pip_version = pip_version_process.stdout.decode().split(" from ")[0].strip()
            result["pip_version"] = pip_version
    except Exception as e:
        result["pip_version_error"] = {"error": repr(e)}

    try:
        pip_freeze_process = subprocess.run([pip_binary, "freeze"], capture_output=True)
        if pip_freeze_process.returncode != 0:
            result["pip_freeze_error"] = {
                "exit_code": pip_freeze_process.returncode,
                "error": pip_freeze_process.stderr.decode().strip(),
            }
        else:
            result["pip_freeze"] = pip_freeze_process.stdout.decode().strip().split("\n")
    except Exception as e:
        result["pip_freeze_error"] = {"error": repr(e)}

    return result


def decompose_dependency(dependency: str) -> Tuple[str, str]:
    """
    Decomposes a dependency returned by pip freeze into a package and a version.

    Currently handles packages from PyPI and git repositories.
    """
    if dependency[:3] == "-e " and dependency[3:7] == "git+":
        split = dependency[3:].split("@")
        if len(split) == 2:
            return tuple(split)
        else:
            return "@".join(split[:-1]), split[-1]
    elif dependency[:3] == "-e ":
        return dependency[3:], ""
    elif "==" in dependency:
        return tuple(dependency.split("=="))

    return dependency, ""


def stats(root_dir: str) -> Dict[str, Any]:
    """
    Statistics for virtual environments that are descendants of the given root directory.
    """
    virtualenvs = get_virtualenvs(root_dir)
    analyses = {
        virtualenv: analyze_virtualenv(virtualenv) for virtualenv in virtualenvs
    }

    python_versions = Counter(
        [analysis.get("python_version", None) for analysis in analyses.values()]
    )

    pip_versions = Counter(
        [analysis.get("pip_version", None) for analysis in analyses.values()]
    )

    dependencies = [
        decompose_dependency(dep)
        for analysis in analyses.values()
        for dep in analysis.get("pip_freeze", [])
    ]

    dependencies_by_package = {}
    for package, version in dependencies:
        if dependencies_by_package.get(package) is None:
            dependencies_by_package[package] = []
        dependencies_by_package[package].append(version)

    dependency_counts = {
        package: Counter(versions)
        for package, versions in dependencies_by_package.items()
    }

    result = {
        "virtualenvs": analyses,
        "statistics": {
            "python_versions": python_versions,
            "pip_versions": pip_versions,
            "dependency_counts": dependency_counts,
        },
    }

    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="busybody: Find all Pythons on your filesystem"
    )
    parser.add_argument(
        "-d",
        "--root-dir",
        default=".",
        help="Directory from which to begin your search",
    )
    parser.add_argument(
        "command",
        choices=["virtualenv?", "virtualenvs", "analyze", "stats"],
        help="Busybody command",
    )
    args = parser.parse_args()

    root_dir = os.path.realpath(os.path.abspath(args.root_dir))
    if args.command == "virtualenv?":
        if is_virtualenv(root_dir):
            sys.exit(0)
        sys.exit(1)
    elif args.command == "virtualenvs":
        json.dump(get_virtualenvs(root_dir), sys.stdout)
    elif args.command == "analyze":
        json.dump(analyze_virtualenv(args.root_dir), sys.stdout)
    elif args.command == "stats":
        json.dump(stats(args.root_dir), sys.stdout)
