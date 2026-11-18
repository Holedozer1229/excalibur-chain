# The Spectral Pairing Theorem

## Submission to arXiv

This package contains the LaTeX source for the manuscript:

**The Spectral Pairing Theorem: A Unified Framework Connecting the Riemann Zeros, Hyperbolic Geometry, and Quantum Information**

by Travis Dale Jones (Aetherion Research Laboratory)

Date: November 18, 2026

## Compilation

To compile the PDF:

```bash
pdflatex spectral_pairing_theorem.tex
pdflatex spectral_pairing_theorem.tex
bibtex spectral_pairing_theorem
pdflatex spectral_pairing_theorem.tex
pdflatex spectral_pairing_theorem.tex
```

## Categories for arXiv

Primary: math.NT (Number Theory)
Secondary: math-ph (Mathematical Physics), quant-ph (Quantum Physics), hep-th (High Energy Physics - Theory)

## Abstract

We present a computational framework that establishes deep connections between the non-trivial zeros of the Riemann zeta function, the spectral gap of Cayley graph Laplacians over finite fields, the Montgomery pair correlation function R₂(w) = 1 - |sin(πw)/(πw)|², and the longitudinal scalar wave equation ∂²φ/∂t² = c²∇²φ.

## Code Repository

All code implementing the framework is available at:
https://github.com/[username]/excalibur-chain

## Key Files

- riemann_solution.py: Non-circular RH framework (21/21 tests)
- hilbert_polya.py: Berry-Keating Hamiltonian
- montgomery_pair_correlation.py: R₂(w) computation
- spectral_graph_shor.py: Cayley graph Laplacian
- scalar_wave_unification.py: Longitudinal scalar waves
- topological_quantum_field.py: TQFT simulator
- bell_state_asm.py: Bell state assembly language
- knot_math.py: Möbius function and knot computation
- theory_of_everything.py: AdS/CFT unification
