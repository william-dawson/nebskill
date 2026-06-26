"""Auto-download Transition1x.h5."""
import argparse
from pathlib import Path

URL           = "https://ndownloader.figshare.com/files/36035789"
EXPECTED_SIZE = 6_600_000_000  # ~6.2 GB


def download(dest: Path) -> None:
    try:
        import requests
        from tqdm import tqdm
    except ImportError as e:
        raise ImportError(
            "nebskill-download needs the dataset tooling (requests, tqdm). "
            "Install the extra: `pip install 'nebskill[dataset]'`. Normal use "
            "reads the bundled cache and needs neither the download nor this."
        ) from e

    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size >= EXPECTED_SIZE:
        existing = dest.stat().st_size
        print(f"Dataset already present at {dest} ({existing / 1e9:.1f} GB)")
        return

    print(f"Downloading Transition1x dataset to {dest}")

    resp = requests.get(URL, stream=True, timeout=60)
    resp.raise_for_status()

    total = int(resp.headers.get("content-length", 0))
    with open(dest, "wb") as f, tqdm(
        total=total or None, unit="B", unit_scale=True, unit_divisor=1024
    ) as bar:
        for chunk in resp.iter_content(chunk_size=1 << 20):
            if chunk:
                f.write(chunk)
                bar.update(len(chunk))

    print(f"Download complete: {dest}")


def main():
    import sys
    parser = argparse.ArgumentParser(description="Download Transition1x dataset")
    parser.add_argument("--dest", default="data/Transition1x.h5",
                        help="Destination path (default: data/Transition1x.h5)")
    args = parser.parse_args()
    try:
        download(Path(args.dest))
    except ImportError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
