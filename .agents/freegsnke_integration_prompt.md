# Integration of FreeGSNKE Functionality Into Bluemira

## Goal

Integrate the Bluemira and FreeGSNKE codes to remove duplication,
improve capability of both codes, and reduce overall maintenance effort.
Capability in Bluemira's equilibirum module should be
moved to/implented in FreeGSNKE,
and Bluemira should use FreeGSNKE as a dependency.
An emphasis should be put on clean, maintainable code,
written in a concise and readable way,
following or improving on the practises and code quality standards seen in Bluemira.

## Roadmap

### 1. Wrap FreeGSNKE's static forward solve functionality for use in Bluemira.

Bluemira can currently only perform backward solve for an equilibrium
(given a plasma shape, position coils).
A good first step in an integration is to wrap the setup and execution
of FreeGSNKE's static forward solve (given coils, calculate plasma properties)
in a Bluemira API.

- [x] **1.1**: Identify necessary FreeGSNKE inputs and Bluemira equivalents,
      including any types that may be missing from Bluemira.
- [x] **1.2**: Design an API for running a forward solve problem in Bluemira.
      This should include expected inputs and outputs and their types.
- [x] **1.3**: Implement the data type and parameter transformations
      required for going from Bluemira objects to FreeGSNKE inputs.
- [x] **1.4**: Implement the solve wrapper that executes the required FreeGNSKE
      routines.
- [x] **1.5**: Implement the data type and parameter transformations
      required for going from FreeGSNKE outputs to Bluemira objects.

## 2. Achieve feature parity between Bluemira & FreeGSNKE's backward solve

There are several difference in the backward solvers in Bluemira and FREEGNSKE.
These difference must be identified
and any features in Bluemira that are missing from FreeGSNKE
must be implemented in FreeGSNKE.

For example, Bluemira uses analytic Greens gradient functions,
whereas FreeGSNKE (via freegs4e) uses a central differences approximation.
The rectangular analytic functions in Bluemira may be generalisable to polygons.
Other examples are Bluemira's solves calculate a `beta_p-li-Ip` profile,
the diagnostic tools used inside the Picard iterator in Bluemira and
the flexible Coil and Coilset objects Bluemira uses.

Note we do not need to look for features in FreeGSNKE that Bluemira is missing,
as the eventual goal is to replace Bluemira's solve with FreeGSNKE's.

- [ ] **2.1**: Identify and list Bluemira backward solve features
      that are missing from FreeGSNKE.
- [ ] **2.2**: Implement the missing features in FreeGSNKE.

## 3. Unify numerical optimisation functionality

Bluemira currently has a generic interface for performing
constrained non-linear numeric optimisation.
The interface can be used to solve optimisation problems using
NLOpt or SciPy.
FreeGSNKE currently uses cvxpy for solving optimisation tasks.
It would be beneficial to unify optimisation routines for consistency.

- [ ] **3.1**: Extract Bluemira's optimisation module into a new package
      that Bluemira depends on.
- [ ] **3.2**: Implement optimisation routines with a `cvxpy` backend.
- [ ] **3.3**: Replace uses of numerical optimisation in FreeGSNKE with new
      optimisation package.

## 4. Replace Bluemira's core equilibria objects with FreeGSNKE wrappers

At this point in the roadmap, all core Grad-Shafranov solve functionality in
Bluemira should be available in FreeGSNKE.
It should be possible to strip out the backend of Bluemira's core equilibria
solvers and replace them with FreeGSNKE routines.
The Bluemira public interface should stay stable, but may be extended.

The key task here is identification of which parts of Bluemira are now
completely covered by FreeGSNKE, and implementing necessary transformations
such that Bluemira objects can be returned from FreeGSNKE outputs.
The largest part of this will likely be replacing Bluemira's backward solve
implementation, with a wrapper around FreeGSNKE's solver.

- [ ] **4.1**: Identify Bluemira data structures whose behaviour is now
      covered by FreeGSNKE.
- [ ] **4.2**: Replace Bluemira data structures and functions
      with wrappers around FreeGSNKE equivalents.

## 5. Implement wrappers around other FreeGSNKE features

FreeGSNKE offers features not available in Bluemira,
e.g., passive structures and evolutive forward solve.
These features may be useful to Bluemira users.
To make use of these features,
Bluemira wrappers around the FreeGSNKE types/functions should be implemented.

- [ ] **5.1**: Identify FreeGSNKE features desired by Bluemira.
- [ ] **5.2**: Implement Bluemira wrappers for corresponding FreeGSNKE
      functions and structures.
