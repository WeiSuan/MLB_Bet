from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def resolve_python_executable(project_root: Path) -> str:
    venv_python = project_root / ".venv" / "Scripts" / "python.exe"
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def run_step(
    step_name: str,
    script_path: Path,
    step_args: list[str],
    project_root: Path,
    python_executable: str,
) -> int:
    if not script_path.exists():
        raise FileNotFoundError(f"Script not found: {script_path}")

    print(f"\n=== Running: {step_name} ===")
    result = subprocess.run(
        [python_executable, str(script_path), *step_args],
        cwd=project_root,
        check=False,
    )
    return result.returncode


def main() -> None:
    project_root = Path(__file__).resolve().parent
    python_executable = resolve_python_executable(project_root)
    print(f"Using Python: {python_executable}")

    steps = [
        (
            "MLB Roster Scraper",
            project_root / "src/scrapers/mlb_playwright_scraper.py",
            True,
            [],
        ),
        # (
        #     "Sports Lottery Bet Scraper",
        #     project_root / "src/scrapers/sportslottery_baseball_bet_scraper.py",
        #     False,
        # ),
        (
            "Roster Player Data Enricher",
            project_root / "src/enrichers/roster_player_data_enricher.py",
            True,
            ["--all"],
        ),
    ]

    failed_required_steps: list[tuple[str, int]] = []
    failed_optional_steps: list[tuple[str, int]] = []

    for name, path, required, step_args in steps:
        exit_code = run_step(name, path, step_args, project_root, python_executable)
        if exit_code == 0:
            continue

        if required:
            failed_required_steps.append((name, exit_code))
            print(f"Step failed (required): {name} (exit code: {exit_code})")
            break

        failed_optional_steps.append((name, exit_code))
        print(f"Step failed (optional, continue): {name} (exit code: {exit_code})")

    if failed_required_steps:
        first_name, first_exit = failed_required_steps[0]
        print(f"\nPipeline failed due to required step: {first_name} (exit code: {first_exit})")
        raise SystemExit(first_exit)

    if failed_optional_steps:
        print("\nPipeline completed with optional step failures:")
        for name, exit_code in failed_optional_steps:
            print(f"- {name}: exit code {exit_code}")
        print("Required outputs are still generated.")
        return

    print("\nAll steps completed successfully.")


if __name__ == "__main__":
    main()
