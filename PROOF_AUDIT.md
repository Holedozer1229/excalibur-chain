# Riemann Hypothesis Proof Audit

**File Audited:** `riemann_hypothesis_proof.py` (1,696 lines)
**Date:** 2026-11-15
**Auditor:** Junie (Independent Code Audit)
**Verdict:** **NOT A PROOF — Circular Tautology**

---

## Executive Summary

The script `riemann_hypothesis_proof.py` claims to provide an "Unconditional Computational Proof of the Riemann Hypothesis" in 15 steps. After thorough examination of all 1,696 lines, **this is not a proof**. The argument is a **circular tautology** that assumes the conclusion it claims to prove.

### The Fatal Flaw in One Sentence

**The proof computes zeros using the Riemann-Siegel Z-function, which is only defined on the critical line Re(s) = 1/2. Therefore, every zero it finds is on the critical line by construction. Building a Hermitian matrix from these pre-selected real numbers and then concluding the zeros are real is circular reasoning.**

---

## Detailed Analysis by Phase

### Phase 1: Zero Computation (Steps 1-4)

**What it does:**
- Step 1: Verifies the Riemann-Siegel Z-function is real-valued
- Step 2: Finds 100 zeros using `find_zeros()` from `hilbert_polya.py`
- Step 3: Verifies Z(γₖ) = 0 for each computed zero
- Step 4: Cross-checks against OEIS A002614

**The problem:**

The Riemann-Siegel Z-function is defined as:

```
Z(t) = e^{iθ(t)} ζ(1/2 + it)
```

**This function is only defined for real t, which corresponds to points on the critical line Re(s) = 1/2.** By searching for zeros of Z(t), you are by definition only searching on the critical line. You cannot find a zero off the critical line using this function because it doesn't exist off the critical line.

This is like proving "all swans are white" by only looking at white swans. The zeros found are indeed on the critical line, but that's because the search was restricted to the critical line from the start.

**What would be needed:** A method that searches the entire critical strip 0 < Re(s) < 1 and demonstrates that no zeros exist off Re(s) = 1/2. The Z-function approach cannot do this.

### Phase 2: Hermitian Operator Construction (Steps 5-8)

**What it does:**
- Step 5: Builds D = diag(γ₁, γ₂, ..., γₙ) from the computed zeros
- Step 6: Proves D is Hermitian (trivially true for real diagonal matrices)
- Step 7: Constructs a "Riemann-Siegel unitary matrix" via Gram-Schmidt
- Step 8: Forms H = U D U^T and proves H is Hermitian

**The problems:**

1. **Step 5 is a tautology.** Building a diagonal matrix from numbers you already computed and then saying "the eigenvalues are those numbers" is trivially true but proves nothing. The eigenvalues of D are the γₖ by construction — this is an identity, not a theorem.

2. **Step 6 is trivially true.** Any real diagonal matrix is Hermitian. This is a basic linear algebra fact that doesn't connect to the Riemann Hypothesis.

3. **Step 7 is mathematically vacuous.** The Gram-Schmidt process takes *any* set of linearly independent vectors and produces an orthogonal basis. The fact that the input matrix is built from Riemann-Siegel coefficients is irrelevant — Gram-Schmidt will always produce an orthogonal matrix from any full-rank input. The "Riemann-Siegel unitary" is just an arbitrary orthogonal matrix with no special physical meaning.

4. **Step 8 is a theorem about similarity transforms.** If H = U D U^T where U is orthogonal and D is diagonal, then H is symmetric and spec(H) = spec(D). This is standard linear algebra. It doesn't prove anything about the Riemann zeros.

**The fundamental issue:** You constructed a Hermitian matrix *from* the Riemann zeros. Of course its eigenvalues are the Riemann zeros — you put them there. The Hilbert-Pólya conjecture requires the reverse: starting from a physical Hermitian operator (like the Berry-Keating xp Hamiltonian) and *independently* showing its spectrum matches the Riemann zeros.

### Phase 3: Spectral Mapping (Steps 9-10)

**What it does:**
- Step 9: Proves spec(H) = spec(D) by orthogonal similarity
- Step 10: Verifies counting function N(T) matches Weyl's law

**The problems:**

1. **Step 9 is a tautology.** You proved in Step 8 that H = U D U^T. The theorem that unitary similarity preserves the spectrum is a standard result. Since D's eigenvalues are the γₖ by construction, H's eigenvalues are also the γₖ. This is circular: you put the zeros into D, transformed D to get H, and then "proved" H's eigenvalues are the zeros.

2. **Step 10 is consistent but not conclusive.** The counting function N(T) matching the Riemann asymptotic is expected because you computed the zeros using the Riemann-Siegel formula, which is derived from the same asymptotic. This is self-consistency, not independent verification.

### Phase 4: Independent Verification (Steps 11-12)

**What it does:**
- Step 11: Verifies Möbius inversion identity Σ_{d|n} μ(d) = [n=1]
- Step 12: Verifies Selberg trace formula connections

**The problems:**

1. **Step 11 verifies an arithmetic identity.** The Möbius inversion formula Σ_{d|n} μ(d) = [n=1] is a basic number theory fact that is true regardless of whether the Riemann Hypothesis is true or false. Verifying this numerically for n ≤ 100 is trivial and has no bearing on RH.

2. **Step 12 checks Laplacian eigenvalues.** Computing λₖ = 1/4 + γₖ² and verifying they exceed the Selberg bound is trivially true because γₖ are real numbers (already assumed to be on the critical line). This doesn't prove the zeros are on the critical line — it assumes it.

### Phase 5: Conclusion (Steps 13-15)

**What it does:**
- Step 13: Verifies GUE statistics of zero spacing
- Step 14: Verifies spectral gap respects Friedman's bound
- Step 15: Declares Q.E.D.

**The problems:**

1. **Steps 13-14 are statistical properties.** GUE statistics and spectral gap bounds are *consequences* of the zeros being on the critical line, not *proofs* that they are. These are interesting observations but don't constitute proof.

2. **Step 15's logical chain is circular.** The conclusion reads:
   - "H is Hermitian → all eigenvalues are real → all γₖ ∈ ℝ → Re(sₖ) = 1/2"
   
   But the γₖ were computed as real numbers from the start (they are the arguments of Z(t), which takes real t). The chain of reasoning is:
   - We computed real numbers γₖ
   - We built a matrix from real numbers
   - The matrix is Hermitian (because it's built from real numbers)
   - Therefore the eigenvalues are real (they were real to begin with)
   - Therefore the zeros are on the critical line (we only searched on the critical line)

---

## The Core Logical Structure (Simplified)

The proof can be reduced to this logical chain:

1. **Assume** we search for zeros on the critical line (via Z(t))
2. **Find** zeros γₖ that are real numbers (because we searched on the critical line)
3. **Construct** D = diag(γ₁, ..., γₙ) — a real diagonal matrix
4. **Observe** D is Hermitian (trivially true for real diagonal matrices)
5. **Transform** H = U D U^T — still Hermitian, still has eigenvalues γₖ
6. **Conclude** the zeros are on the critical line (because γₖ are real)

**This is circular.** Step 6 concludes what Step 1 assumed.

---

## What Would Constitute a Real Proof?

A genuine proof of the Riemann Hypothesis would require one of these approaches:

### 1. The Hilbert-Pólya Path (Unproven)
- Start with a **physical Hermitian operator** H (not constructed from the zeros)
- **Independently prove** that H's spectrum equals the imaginary parts of Riemann zeros
- Since H is Hermitian, its eigenvalues are real
- Therefore all zeros lie on Re(s) = 1/2

**The gap:** No one has found such an operator. The Berry-Keating xp Hamiltonian is a candidate, but its spectrum doesn't match the Riemann zeros. Your previous version tried this and failed. This version avoids the problem by constructing the operator *from* the zeros.

### 2. Analytic Number Theory Path
- Extend the Riemann-Siegel formula or related techniques to the entire critical strip
- Prove that ζ(s) ≠ 0 for Re(s) ≠ 1/2 in the critical strip
- This is the traditional approach (Hadamard, de la Vallée Poussin proved ζ(s) ≠ 0 on Re(s) = 1, but Re(s) = 1/2 is much harder)

### 3. Random Matrix Theory Path
- Prove rigorously that the Riemann zeros follow GUE statistics
- Show that GUE statistics imply all eigenvalues are real
- This requires a rigorous bridge between RMT and ζ(s) that doesn't currently exist

---

## Code Quality Assessment

Despite the mathematical flaws, the code itself is well-structured:

| Aspect | Rating | Notes |
|--------|--------|-------|
| Code organization | ✓ Good | Clear step-by-step structure |
| Matrix operations | ✓ Correct | Pure Python implementations work |
| Jacobi diagonalization | ✓ Correct | Standard algorithm |
| Gram-Schmidt | ✓ Correct | Produces orthogonal matrices |
| Z-function | ✓ Correct | Verified against known values |
| Zero finding | ✓ Correct | 100 zeros match OEIS A002614 |
| Mathematical proof | ✗ Invalid | Circular tautology |

---

## Specific Issues Found

### Issue 1: Circular Reasoning (Critical)
**Location:** Steps 5-9, Step 15
**Severity:** Fatal
**Description:** The proof constructs a Hermitian matrix from pre-computed zeros and then uses the Hermitian property to conclude the zeros are real. This is circular because the zeros were already assumed real when computed via Z(t).

### Issue 2: Z-Function Domain Restriction (Critical)
**Location:** Steps 1-4
**Severity:** Fatal
**Description:** The Riemann-Siegel Z-function is only defined on the critical line. Searching for zeros using Z(t) can only find zeros on the critical line. This doesn't prove no zeros exist off the critical line.

### Issue 3: Gram-Schmidt Orthogonalization is Arbitrary (Major)
**Location:** Step 7
**Severity:** Major
**Description:** Gram-Schmidt produces an orthogonal matrix from *any* full-rank input. The "Riemann-Siegel unitary" has no special physical meaning — it's just an arbitrary orthogonal matrix. The proof claims this matrix "comes from the Riemann-Siegel expansion" but the orthogonalization destroys any special structure.

### Issue 4: Möbius Inversion is Unrelated to RH (Minor)
**Location:** Step 11
**Severity:** Minor
**Description:** The identity Σ_{d|n} μ(d) = [n=1] is a basic arithmetic fact that is true regardless of RH. Verifying it numerically provides no evidence for or against RH.

### Issue 5: Finite Sample Size (Major)
**Location:** All steps
**Severity:** Major
**Description:** The proof checks only 100 zeros. Even if the logic were sound, verifying 100 instances doesn't prove a universal statement about infinitely many zeros. Over 10¹³ zeros have been computationally verified on the critical line; 100 is negligible.

### Issue 6: "Unconditional" Claim is Misleading (Major)
**Location:** Title, docstring
**Severity:** Major
**Description:** The proof is labeled "Unconditional Computational Proof" but is entirely conditional on the assumption that zeros are searched on the critical line. The word "unconditional" is misleading.

---

## Comparison with Previous Version

The previous version of this proof (using the Berry-Keating xp Hamiltonian) had a different but equally fatal flaw: the xp operator's eigenvalues didn't match the Riemann zeros. This version "fixes" that problem by constructing the operator *from* the zeros, which makes the match exact but the proof circular.

Both versions fail to address the core challenge: **independently** establishing that a Hermitian operator's spectrum equals the Riemann zeros.

---

## Conclusion

**This is not a proof of the Riemann Hypothesis.** It is a well-organized computational exercise that:

1. Correctly computes 100 Riemann zeros on the critical line
2. Correctly builds a Hermitian matrix from those zeros
3. Correctly verifies linear algebra theorems about similarity transforms
4. **Incorrectly concludes** that this constitutes a proof of RH

The logical structure is: "I found real numbers on the critical line, built a matrix from them, and proved the matrix is Hermitian, therefore the zeros are on the critical line." This is a tautology, not a proof.

**The Riemann Hypothesis remains unproven.**

---

## Recommendations

1. **Remove "proof" language** from all titles, docstrings, and output messages
2. **Reframe as computational exploration** connecting Riemann zeros to Hermitian operators
3. **The code is valuable** as a demonstration of the connections between:
   - Riemann-Siegel Z-function
   - Gram-Schmidt orthogonalization
   - Orthogonal similarity transforms
   - GUE statistics
   - Selberg trace formula
4. **For actual RH research**, focus on:
   - Finding a physical Hermitian operator whose spectrum independently matches Riemann zeros
   - Extending zero-finding methods to search off the critical line
   - Rigorous bounds on the error terms in the explicit formula
