"""Calculator backends for nebskill.

Two backends, selected by `calculator.backend` in the config:
  - mace  : MACE-OFF23 ML potential (fast, the default)
  - pyscf : DFT at the dataset's level of theory (ωB97X/6-31G(d)) for
            reproducing / probing the Transition1x reference values

torch/mace/pyscf are imported lazily so importing this module only pulls what
the chosen backend needs. ASE is a core dependency and is imported eagerly.
"""
from ase.calculators.calculator import Calculator, all_changes


def make_calculator(config: dict, charge: int = 0, spin: int = 0):
    """Return an ASE calculator for the configured backend.

    charge/spin are only used by the pyscf backend; mace ignores them.
    """
    backend = config.get("calculator", {}).get("backend", "mace")
    if backend == "mace":
        return _make_mace(config)
    if backend == "pyscf":
        calc = config.get("calculator", {})
        return PySCFCalculator(
            xc=calc.get("xc", "wb97x"),
            basis=calc.get("basis", "6-31g(d)"),
            charge=charge,
            spin=spin,
        )
    raise ValueError(f"Unknown calculator backend: {backend!r} (use 'mace' or 'pyscf')")


def _make_mace(config: dict):
    import torch
    from mace.calculators import mace_off

    calc = config.get("calculator", {})
    device = calc.get("device", "auto")
    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    return mace_off(model=calc.get("model_size", "medium"),
                    device=device,
                    default_dtype=calc.get("dtype", "float64"))


class PySCFCalculator(Calculator):
    """ASE calculator wrapping a PySCF DFT single point (energy + forces).

    Energies are returned in eV and forces in eV/Å, matching ASE and the
    Transition1x reference units. Uses RKS for closed-shell (spin=0) and UKS
    otherwise. `spin` is the ASE/PySCF convention n_alpha - n_beta = 2S.
    """

    implemented_properties = ["energy", "forces"]

    def __init__(self, xc: str = "wb97x", basis: str = "6-31g(d)",
                 charge: int = 0, spin: int = 0, **kwargs):
        super().__init__(**kwargs)
        self.xc = xc
        self.basis = basis
        self.charge = charge
        self.spin = spin

    def calculate(self, atoms=None, properties=("energy",),
                  system_changes=all_changes):
        super().calculate(atoms, properties, system_changes)

        from pyscf import gto, dft
        from ase.units import Hartree, Bohr

        mol = gto.M(
            atom=[(s, tuple(p)) for s, p in
                  zip(self.atoms.get_chemical_symbols(),
                      self.atoms.get_positions())],
            basis=self.basis,
            charge=self.charge,
            spin=self.spin,
            unit="Angstrom",
        )
        mf = dft.RKS(mol) if self.spin == 0 else dft.UKS(mol)
        mf.xc = self.xc
        energy_ha = mf.kernel()
        grad_ha_bohr = mf.nuc_grad_method().kernel()    # dE/dR, Hartree/Bohr

        self.results = {
            "energy": float(energy_ha) * Hartree,
            "forces": -grad_ha_bohr * (Hartree / Bohr),
        }
