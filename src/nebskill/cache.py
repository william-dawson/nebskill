"""Access the bundled reaction cache (endpoints + TS + reference barrier).

The skills only ever need each reaction's reactant / product / transition-state
geometries and its reference barrier — a few MB for ~1000 reactions. So nebskill
ships that as a cache and the runtime tools read it directly, instead of
downloading and indexing the full 6.2 GB Transition1x HDF5. Regenerate the cache
(e.g. to change the count or the seed) with `nebskill-build-cache` against the
full dataset; that is the only step that needs h5py and the HDF5 file.
"""
import json
from functools import lru_cache
from importlib.resources import files

CACHE_NAME = "reactions_cache.json"


@lru_cache(maxsize=1)
def load_cache() -> dict:
    """The full cache: {'seed', 'n', 'level_of_theory', 'reactions': {id: data}}."""
    with files("nebskill").joinpath(CACHE_NAME).open("r") as f:
        return json.load(f)


def reaction_ids() -> list:
    """Sorted list of cached reaction ids."""
    return sorted(int(k) for k in load_cache()["reactions"])


def get_reaction(reaction_id: int) -> dict | None:
    """One cached reaction's endpoints dict (reactant/product/ts_reference +
    reference barrier), or None if that id is not in the cache."""
    return load_cache()["reactions"].get(str(reaction_id))


def summary() -> dict:
    c = load_cache()
    return {"n": c.get("n"), "seed": c.get("seed"),
            "level_of_theory": c.get("level_of_theory"),
            "ids": reaction_ids()}
