# ---
# jupyter:
#   jupytext:
#     cell_metadata_filter: tags,-all
#     notebook_metadata_filter: -jupytext.text_representation.jupytext_version
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#   kernelspec:
#     display_name: Python 3 (ipykernel)
#     language: python
#     name: python3
# ---

# %% tags=["remove-cell"]
# SPDX-FileCopyrightText: 2024-present Bluemira contributors
#
# SPDX-License-Identifier: LGPL-2.1-or-later

"""
Inverse Grad-Shafranov equilibrium solve delegating to FreeGSNKE.
"""

# %% [markdown]
# # Inverse Grad-Shafranov Solve with FreeGSNKE
#
# This tutorial demonstrates how to perform **static inverse Grad-Shafranov (GS)**
# equilibrium solves in Bluemira by delegating to FreeGSNKE's constrained inverse
# optimizer (`Inverse_optimizer` and `NKGSsolver.inverse_solve`).
#
# ## What is an Inverse Equilibrium Solve?
# In an **inverse equilibrium solve**, we seek active coil currents that produce a
# desired plasma shape and magnetic topology. Given:
# - Desired magnetic nulls (divertor X-points: $B_r = 0, B_z = 0$)
# - Isoflux boundary targets: $\psi(R_i, Z_i) = \psi_{\text{ref}}$
# - Direct flux values ($\psi(R_k, Z_k) = \psi_k$) or local field targets ($B_r, B_z$)
# - Optional coil current limits and coil force constraints
#
# FreeGSNKE solves a coupled nonlinear optimization problem in which coil currents
# and plasma flux are iteratively updated until both the Grad-Shafranov equation:
# $$\Delta^* \psi = -\mu_0 R^2 p'(\psi) - F F'(\psi)$$
# and the target magnetic constraints are satisfied.
#
# Bluemira provides three seamless interfaces:
# 1. Direct in-place method: `Equilibrium.inverse_solve(constraints, ...)`
# 2. Configurable runner class: `InverseGSSolver`
# 3. Drop-in backend delegation in `PicardIterator(opt_problem, backend="freegsnke")`

# %%
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from bluemira.base.file import get_bluemira_path
from bluemira.display.auto_config import plot_defaults
from bluemira.equilibria.coils import Circuit, Coil, CoilSet
from bluemira.equilibria.equilibrium import Equilibrium
from bluemira.equilibria.freegsnke_bridge import InverseGSSolver, InverseSolveResult
from bluemira.equilibria.grid import Grid
from bluemira.equilibria.limiter import Limiter
from bluemira.equilibria.optimisation.constraints import (
    FieldNullConstraint,
    IsofluxConstraint,
    MagneticConstraintSet,
)
from bluemira.equilibria.optimisation.problem import TikhonovCurrentCOP
from bluemira.equilibria.profiles import CustomProfile
from bluemira.equilibria.solve import PicardIterator

plot_defaults()

# %% [markdown]
# ## 1. Build the Tokamak Coilset & Limiter
#
# We model a realistic MAST-U spherical tokamak configuration using FreeGSNKE's machine
# definition:
# - Coils loaded from `MAST-U_like_active_coils.json` grouped into 12 circuits.
# - The Central Solenoid (CS) provides initial flux and is held fixed during solve.
# - Vacuum vessel first wall limiter loaded from `MAST-U_like_limiter.json`.

# %%
path = get_bluemira_path("equilibria", subfolder="examples")
coils_file = Path(path, "MAST-U_like_active_coils.json")
limiter_file = Path(path, "MAST-U_like_limiter.json")

with open(coils_file) as f:
    coil_dict = json.load(f)

with open(limiter_file) as f:
    limiter_data = json.load(f)

limiter = Limiter(
    [pt["R"] for pt in limiter_data],
    [pt["Z"] for pt in limiter_data],
)

# Initial active coil currents (approximate pre-optimization values)
circuit_currents = {
    "Solenoid": 5000.0,
    "PX": 3696.81,
    "D1": 6941.24,
    "D2": 4390.86,
    "D3": 2924.36,
    "Dp": -2488.20,
    "D5": 249.21,
    "D6": -315.00,
    "D7": 511.08,
    "P4": -3564.38,
    "P5": -3954.24,
    "P6": 0.0,
}

circuits = []
for name, data in coil_dict.items():
    coils = []
    if name == "Solenoid":
        for i, (r, z) in enumerate(zip(data["R"], data["Z"], strict=False)):
            coil = Coil(
                r,
                z,
                current=0.0,
                dx=data["dR"] / 2.0,
                dz=0.00489474,
                ctype="CS",
                name=f"{name}_{i}",
            )
            coils.append(coil)
    else:
        for i, (r1, z1, r2, z2) in enumerate(
            zip(
                data["1"]["R"],
                data["1"]["Z"],
                data["2"]["R"],
                data["2"]["Z"],
                strict=False,
            )
        ):
            coils.extend([
                Coil(
                    r1,
                    z1,
                    current=0.0,
                    dx=data["1"]["dR"] / 2.0,
                    dz=data["1"]["dZ"] / 2.0,
                    ctype="PF",
                    name=f"{name}U_{i}",
                ),
                Coil(
                    r2,
                    z2,
                    current=0.0,
                    dx=data["2"]["dR"] / 2.0,
                    dz=data["2"]["dZ"] / 2.0,
                    ctype="PF",
                    name=f"{name}L_{i}",
                ),
            ])
    circ = Circuit(*coils)
    circ.current = circuit_currents.get(name, 0.0)
    circuits.append(circ)

coilset = CoilSet(*circuits)
print(f"Constructed CoilSet with {len(circuits)} circuits and attached MAST-U limiter.")

# %% [markdown]
# ## 2. Define Plasma Source Profiles & Computational Grid
#
# We load normalized reference profiles from an EQDSK file using Bluemira's COCOS
# interface (`from_cocos=7` for FreeGSNKE Wb/rad convention):
# - Total plasma current: $I_p = 600\,\text{kA}$
# - Major radius: $R_0 = 0.85\,\text{m}$
# - Vacuum toroidal field: $B_0 = 0.588\,\text{T}$

# %%
eqdsk_file = Path(path, "MASTU-FREEGSNKE.eqdsk")
ref_eq = Equilibrium.from_eqdsk(eqdsk_file, from_cocos=7)

psi_n = np.linspace(0.0, 1.0, 50)
profiles = CustomProfile(
    ref_eq.profiles.pprime(psi_n),
    ref_eq.ffprime(psi_n),
    R_0=0.85,
    B_0=0.588,
    I_p=6.0e5,
)

grid = Grid(0.1, 2.0, -2.2, 2.2, nx=65, nz=129)
eq = Equilibrium(coilset, grid, profiles, limiter=limiter, force_symmetry=True)

# Exclude Central Solenoid from control so its current remains fixed
eq.coilset.control = [n for n in eq.coilset.name if not n.startswith("Solenoid")]
print(f"Equilibrium initialized on grid ({grid.nx} x {grid.nz}).")
print(f"Controllable circuits: {len(eq.coilset.control)} (Solenoid fixed at 5 kA).")

# Record initial currents for before/after comparison
initial_currents = {
    name: float(np.asarray(circ.current).flat[0])
    for name, circ in zip(coil_dict.keys(), circuits, strict=False)
}

# %% [markdown]
# ## 3. Define Magnetic Targets (Constraints)
#
# We set up two classes of magnetic shape constraints:
# 1. **Divertor X-Points (`FieldNullConstraint`)**:
#    Upper/lower nulls at $(0.6, \pm 1.1)\,\text{m}$.
# 2. **Boundary Contour (`IsofluxConstraint`)**: Points along midplane and boundary
#    required to share the poloidal flux value of the primary X-point.

# %%
rx, zx = 0.6, 1.1
nulls = FieldNullConstraint(
    x=np.array([rx, rx]),
    z=np.array([zx, -zx]),
)

# Boundary contour points with reference point at the upper X-point
isoflux = IsofluxConstraint(
    x=np.array([0.34, 1.40, 1.00, 1.00]),
    z=np.array([0.00, 0.00, 2.00, -2.00]),
    ref_x=rx,
    ref_z=zx,
)

constraints = MagneticConstraintSet([nulls, isoflux])
print(
    f"MagneticConstraintSet configured with {len(constraints.constraints)} constraints."
)

# %% [markdown]
# ## 4. Execute Inverse Solve (In-Place Method with Callback)
#
# We solve the inverse problem using `eq.inverse_solve()`, supplying a callback
# hook `(iteration, eq, residual)` to track convergence across iterations.

# %%
history: list[dict[str, float]] = []


def iteration_callback(iteration: int, _current_eq: object, residual: float) -> None:
    """Record convergence residual at each outer iteration."""
    history.append({"iteration": iteration, "residual": float(residual)})
    print(f"  [Iter {iteration:02d}] Relative Residual = {residual:.3e}")


print("Starting FreeGSNKE Inverse Solve...")
result: InverseSolveResult = eq.inverse_solve(
    constraints,
    max_iterations=20,
    target_relative_tolerance=1e-5,
    callback=iteration_callback,
    suppress=True,
)

print("\n" + "=" * 50)
print("Inverse Solve Result:")
print(f"  Converged:       {result.converged}")
print(f"  Iterations:      {result.iterations}")
print(f"  Relative Error:  {result.relative_error:.2e}")
print(f"  Elapsed Time:    {result.time_taken:.3f} s")
print(f"  Psi Axis:        {result.psi_axis:.4f} Wb/rad")
print(f"  Psi Boundary:    {result.psi_boundary:.4f} Wb/rad")
print(f"  Optimized Coils: {len(result.coil_currents)}")
print("=" * 50)

# %% [markdown]
# ## 5. Alternative: Object-Oriented `InverseGSSolver` Runner
#
# For modular workflows, `InverseGSSolver` wraps the inverse solve in an OO runner:

# %%
runner = InverseGSSolver(
    eq,
    constraints=constraints,
    target_relative_tolerance=1e-5,
    max_iterations=10,
)
runner_result = runner.solve(suppress=True)
print(
    f"InverseGSSolver completed in {runner_result.iterations} iterations "
    f"(rel error: {runner_result.relative_error:.2e})."
)

# %% [markdown]
# ## 6. PicardIterator Backend Delegation (`backend="freegsnke"`)
#
# For drop-in compatibility with existing Bluemira optimisation loops, `PicardIterator`
# accepts `backend="freegsnke"` to transparently delegate each Picard step:

# %%
opt_problem = TikhonovCurrentCOP(eq, constraints, gamma=1e-8)
iterator = PicardIterator(opt_problem, backend="freegsnke", fixed_coils=True, maxiter=3)
picard_result = iterator()
print(
    f"PicardIterator ('freegsnke' backend) finished: "
    f"{picard_result.n_evals} evaluations performed."
)

# %% [markdown]
# ## 7. Visualizing the Converged Equilibrium & Coil Currents
#
# ### Plot 1: 2D Magnetic Flux Topology, Limiter, & Target Constraint Points
# Total poloidal flux contours $\psi(R, Z)$, coils, axis, separatrix, limiter,
# target X-points (red stars) and isoflux targets (diamonds):

# %%
fig, ax = plt.subplots(figsize=(7, 9))
eq.plot(ax=ax)
limiter.plot(ax=ax)

# Overlay constraint targets
ax.scatter(
    [rx, rx],
    [zx, -zx],
    color="red",
    marker="*",
    s=150,
    zorder=10,
    label="X-Points",
)
ax.scatter(
    [0.34, 1.40, 1.00, 1.00],
    [0.00, 0.00, 2.00, -2.00],
    color="darkorange",
    marker="D",
    s=50,
    zorder=10,
    label="Isoflux Targets",
)

ax.set_title("MAST-U Inverse Solve: Converged Flux & Constraints")
ax.set_xlabel("R [m]")
ax.set_ylabel("Z [m]")
ax.set_aspect("equal")
ax.legend(loc="upper right")
plt.tight_layout()
plt.show()

# %% [markdown]
# ### Plot 2: Coil Current Comparison (Before vs. After Optimization)
# Comparison of circuit currents before and after the inverse solve:

# %%
coil_names = list(coil_dict.keys())
initial_vals = [initial_currents[k] * 1e-3 for k in coil_names]
final_vals = [float(np.asarray(circ.current).flat[0]) * 1e-3 for circ in circuits]

x_indices = np.arange(len(coil_names))
width = 0.38

fig, ax = plt.subplots(figsize=(12, 5))
rects1 = ax.bar(
    x_indices - width / 2,
    initial_vals,
    width,
    label="Initial [kA]",
    color="steelblue",
)
rects2 = ax.bar(
    x_indices + width / 2,
    final_vals,
    width,
    label="Optimized [kA]",
    color="coral",
)

ax.set_title("Circuit Currents: Initial vs. Post-Inverse Solve")
ax.set_xlabel("Circuit Name")
ax.set_ylabel("Current [kA]")
ax.set_xticks(x_indices)
ax.set_xticklabels(coil_names, rotation=30)
ax.axhline(0, color="gray", lw=0.8, linestyle="--")
ax.legend()
ax.grid(visible=True, alpha=0.3, axis="y")
plt.tight_layout()
plt.show()

# %% [markdown]
# ### Plot 3: Convergence History & Midplane Flux Distribution
# Convergence of relative residual across iterations and midplane flux $\psi(R, 0)$:

# %%
fig, axes = plt.subplots(1, 2, figsize=(13, 5))

# 1. Convergence History
if history:
    iters = [h["iteration"] for h in history]
    resids = [h["residual"] for h in history]
    axes[0].semilogy(iters, resids, "b-o", lw=2, markersize=6)
    axes[0].set_xlabel("Iteration")
    axes[0].set_ylabel("Relative Residual")
    axes[0].set_title("Inverse Solve Convergence History")
    axes[0].grid(visible=True, which="both", alpha=0.3)
else:
    axes[0].text(0.5, 0.5, "Converged in 1 iteration", ha="center", va="center")

# 2. Midplane Flux Decomposition
r_mid = np.linspace(eq.grid.x_min, eq.grid.x_max, 100)
z_mid = np.zeros_like(r_mid)
axes[1].plot(r_mid, eq.psi(r_mid, z_mid), "b-", lw=2, label=r"Total $\psi(R, 0)$")
axes[1].plot(
    r_mid,
    eq.coilset.psi(r_mid, z_mid),
    "g--",
    lw=1.5,
    label=r"Coil $\psi_{\mathrm{coil}}$",
)
axes[1].plot(
    r_mid,
    eq.plasma.psi(r_mid, z_mid),
    "m:",
    lw=1.5,
    label=r"Plasma $\psi_{\mathrm{plasma}}$",
)
axes[1].set_xlabel("R [m]")
axes[1].set_ylabel(r"Poloidal Flux $\psi$ [$\mathrm{Wb}$]")
axes[1].set_title("Midplane Poloidal Flux Decomposition")
axes[1].legend()
axes[1].grid(visible=True, alpha=0.3)

plt.tight_layout()
plt.show()
