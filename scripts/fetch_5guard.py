"""Fetch the exact upstream 5Guard revision used by SecGuard."""

from pathlib import Path
import subprocess


REPOSITORY = "https://github.com/mehdibolourian/5Guard.git"
REVISION = "adadaccfcb6febfbf9e73eaf83541a9d20e7c5d0"


def main() -> None:
    destination = Path("external/5guard")
    if destination.exists():
        print(f"Already present: {destination}")
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "clone", "--depth", "1", REPOSITORY, str(destination)],
        check=True,
    )
    subprocess.run(
        ["git", "checkout", REVISION], cwd=destination, check=True
    )
    print(f"Checked out 5Guard revision {REVISION}")


if __name__ == "__main__":
    main()

