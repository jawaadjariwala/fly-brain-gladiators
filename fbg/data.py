"""Download and load the MaleCNS connectome.

Data source: MaleCNS v1.0, HHMI Janelia FlyEM in collaboration with Google
Research, the University of Cambridge and MRC LMB (2026). Licensed CC-BY.

Direct Google Storage downloads; no authentication required.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.request import urlopen

BASE = (
    "https://storage.googleapis.com/flyem-male-cns/v1.0"
    "/connectome-data/flat-connectome"
)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@dataclass(frozen=True)
class Source:
    name: str
    filename: str
    approx_mb: int

    @property
    def url(self) -> str:
        return f"{BASE}/{self.filename}"

    @property
    def path(self) -> Path:
        return DATA_DIR / self.filename


SOURCES = {
    # neuron-to-neuron connection strengths — the edge list
    "weights": Source("weights", "connectome-weights-male-cns-v1.0-minconf-0.5.feather", 1100),
    # curated annotations: cell type, class, side, neuropil
    "annotations": Source("annotations", "body-annotations-male-cns-v1.0-minconf-0.5.feather", 13),
    # per-neuron neurotransmitter predictions — gives us the sign
    "neurotransmitters": Source("neurotransmitters", "body-neurotransmitters-male-cns-v1.0.feather", 42),
}

# The 6.8 GB syn-partners file holds individual synapse locations.
# Not needed: the simulation works on aggregated neuron-to-neuron weights.


def download(source: Source, *, force: bool = False) -> Path:
    """Fetch one source file, streaming with progress. Skips if already present."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if source.path.exists() and not force:
        mb = source.path.stat().st_size / 1e6
        print(f"  {source.name:18} already present ({mb:,.0f} MB)")
        return source.path

    tmp = source.path.with_suffix(source.path.suffix + ".partial")
    print(f"  {source.name:18} downloading ~{source.approx_mb:,} MB")

    with urlopen(source.url) as response, open(tmp, "wb") as out:
        total = int(response.headers.get("Content-Length", 0))
        done = 0
        while chunk := response.read(1 << 20):
            out.write(chunk)
            done += len(chunk)
            if total:
                pct = 100 * done / total
                print(f"\r  {' ' * 18} {pct:5.1f}%  {done/1e6:,.0f}/{total/1e6:,.0f} MB",
                      end="", flush=True)
        print()

    tmp.rename(source.path)
    return source.path


def download_all(*, force: bool = False) -> dict[str, Path]:
    print(f"MaleCNS v1.0 → {DATA_DIR}")
    return {name: download(src, force=force) for name, src in SOURCES.items()}


if __name__ == "__main__":
    download_all(force="--force" in sys.argv)
