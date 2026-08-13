"""Download the public MIT-licensed Open5GS intrusion-detection dataset."""

from pathlib import Path
from urllib.request import urlretrieve


BASE_URL = "https://raw.githubusercontent.com/saeidsheikhi/5G-Intrusion-Detection-Dataset/main/data"
FILES = ("Train_subset_1.csv", "Train_subset_2.csv", "Test_Data.csv")


def main() -> None:
    destination = Path("data/raw")
    destination.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        target = destination / name
        if target.exists():
            print(f"Already present: {target}")
            continue
        print(f"Downloading {name} ...")
        urlretrieve(f"{BASE_URL}/{name}", target)
        print(f"Saved: {target}")


if __name__ == "__main__":
    main()

