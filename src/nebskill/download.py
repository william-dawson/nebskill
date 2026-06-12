"""Auto-download Transition1x.h5 with resume support."""
import argparse
import sys
from pathlib import Path

import requests
from tqdm import tqdm

URL           = "https://ndownloader.figshare.com/files/36035789"
EXPECTED_SIZE = 6_600_000_000  # ~6.2 GB


def download(dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    existing = dest.stat().st_size if dest.exists() else 0

    if existing >= EXPECTED_SIZE:
        print(f"Dataset already present at {dest} ({existing / 1e9:.1f} GB)")
        return

    headers = {"Range": f"bytes={existing}-"} if existing else {}
    mode    = "ab" if existing else "wb"

    print(f"Downloading Transition1x dataset to {dest}")
    if existing:
        print(f"  Resuming from {existing / 1e9:.1f} GB")

    resp = requests.get(URL, headers=headers, stream=True, timeout=60)
    resp.raise_for_status()

    total = int(resp.headers.get("content-length", 0)) + existing
    with open(dest, mode) as f, tqdm(
        total=total, initial=existing, unit="B", unit_scale=True, unit_divisor=1024
    ) as bar:
        for chunk in resp.iter_content(chunk_size=1 << 20):
            f.write(chunk)
            bar.update(len(chunk))

    print(f"Download complete: {dest}")


def main():
    parser = argparse.ArgumentParser(description="Download Transition1x dataset")
    parser.add_argument("--dest", default="data/Transition1x.h5",
                        help="Destination path (default: data/Transition1x.h5)")
    args = parser.parse_args()
    download(Path(args.dest))


if __name__ == "__main__":
    main()
