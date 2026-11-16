// e91_handshake.qasm — E91 Entanglement Handshake for Aetherion-Excalibur P2P
//
// Purpose: Peer identity verification + session key establishment via quantum
// key distribution (QKD) using entangled Bell pairs in the E91 protocol.
//
// Protocol overview:
//   1. A trusted source (or either peer) generates entangled Bell pairs:
//      |Φ+⟩ = (|00⟩ + |11⟩) / √2
//   2. Alice receives qubit A, Bob receives qubit B from each pair.
//   3. Both parties measure their qubits in randomly chosen bases (a, b ∈ {0,1,2}).
//   4. Sifting: reveal bases publicly, keep measurement results where bases match.
//   5. CHSH test: verify entanglement by computing S parameter from a subset.
//      If |S| > 2, quantum correlation is confirmed (classical limit is S ≤ 2).
//   6. Key extraction: remaining sifted bits form the shared secret key.
//
// OpenQASM 3 circuit definition for one E91 round.
// In practice, N rounds are repeated to build a key of length K bits.

OPENQASM 3.0;
include "stdgates.inc";

// Number of Bell pairs generated per handshake round
const int[32] N_PAIRS = 64;

// Measurement bases for CHSH inequality (optimal for |Φ+⟩):
//   Alice: a0 = 0° (0),       a1 = 90° (π/2)
//   Bob:   b0 = 45° (π/4),    b1 = -45° (-π/4)
// These angles maximize the CHSH violation: S = 2√2 ≈ 2.828
// Correlation: E(α,β) = cos(α - β)

/// Generate a single Bell pair |Φ+⟩ = (|00⟩ + |11⟩) / √2
///
/// Input:  q[0] → Alice's qubit,  q[1] → Bob's qubit
/// Both start in |0⟩. After H on q[0] and CX(q[0], q[1]),
/// the state is the maximally entangled Bell state |Φ+⟩.
def generate_bell_pair(qubit[2] q) {
    h q[0];
    cx q[0], q[1];
}

/// Measure a qubit in a rotated basis.
///
/// The E91 protocol uses three measurement settings per party.
/// For CHSH, we use two settings:
///   angle = 0  → measure in Z basis (computational basis)
///   angle = π/4 → rotate by Ry(-θ) then measure in Z basis
///
/// This effectively measures in the X-Z plane at the given angle.
def measure_in_basis(output bit result, qubit q, const float[64] angle) {
    if (angle != 0.0) {
        ry(-angle) q;
    }
    result = measure q;
}

/// Full E91 handshake circuit for N entangled pairs.
///
/// Returns:
///   alice_results[N] — Alice's measurement outcomes
///   bob_results[N]   — Bob's measurement outcomes
///   alice_bases[N]   — Alice's randomly chosen bases (classical)
///   bob_bases[N]     — Bob's randomly chosen bases (classical)
///
/// The classical basis choices are inputs (simulating random number generation).
/// In a real deployment, these come from a hardware RNG or the GHZ beacon.
def e91_handshake(
    input bit[N_PAIRS] alice_basis_choices,
    input bit[N_PAIRS] bob_basis_choices,
    output bit[N_PAIRS] alice_results,
    output bit[N_PAIRS] bob_results
) {
    // Qubits: 2 per Bell pair (Alice + Bob)
    qubit[2 * N_PAIRS] q;
    
    // --- Step 1: Generate N entangled Bell pairs ---
    for int i in [0:N_PAIRS-1] {
        generate_bell_pair(q[2*i:2*i+2]);
    }
    
    // --- Step 2: Measure in randomly chosen bases ---
    // Alice's angles: 0° (basis 0) or 45° (basis 1)
    // Bob's angles: 22.5° (basis 0) or 67.5° (basis 1)
    for int i in [0:N_PAIRS-1] {
        // Alice measures qubit 2*i
        // Angles: a0 = 0, a1 = π/2
        float[64] alice_angle = (alice_basis_choices[i] == 0) ? 0.0 : (M_PI / 2.0);
        alice_results[i] = measure_in_basis(q[2*i], alice_angle);
        
        // Bob measures qubit 2*i+1
        // Angles: b0 = π/4, b1 = -π/4
        float[64] bob_angle = (bob_basis_choices[i] == 0) ? (M_PI / 4.0) : (-M_PI / 4.0);
        bob_results[i] = measure_in_basis(q[2*i+1], bob_angle);
    }
}

/// CHSH correlation computation (classical post-processing).
///
/// After measurement, Alice and Bob publicly reveal their basis choices
/// (not results) and compute the CHSH S parameter:
///
///   S = E(a0,b0) + E(a0,b1) + E(a1,b0) - E(a1,b1)
///
/// where E(a,b) = P(same|a,b) - P(different|a,b)
///
/// Quantum mechanics predicts S = 2√2 ≈ 2.828 for |Φ+⟩.
/// Classical local hidden-variable theories are bounded by |S| ≤ 2.
///
/// This function is documented here for the classical post-processing step;
/// in OpenQASM 3 it would be implemented in the host language (Python).
//
// Classical post-processing pseudocode:
//
//   def compute_chsh(alice_results, bob_results, alice_bases, bob_bases):
//       """Compute CHSH S parameter from measurement data."""
//       correlations = {}
//       for i in range(N_PAIRS):
//           key = (alice_bases[i], bob_bases[i])
//           same = (alice_results[i] == bob_results[i])
//           correlations[key] = correlations.get(key, [0, 0])
//           correlations[key][int(not same)] += 1  # count mismatches
//           correlations[key][1] += 1  # total
//       
//       def E(a, b):
//           counts = correlations.get((a, b), [0, 1])
//           return (counts[1] - counts[0]) / counts[1]  # P(same) - P(diff)
//       
//       S = E(0,0) + E(0,1) + E(1,0) - E(1,1)
//       return S
//
//   def extract_key(alice_results, bob_results, alice_bases, bob_bases):
//       """Extract shared secret key from sifted bits."""
//       key = []
//       for i in range(N_PAIRS):
//           # Keep bits where bases were compatible for key generation
//           # (e.g., both used basis 0, which gives correlated results)
//           if alice_bases[i] == 0 and bob_bases[i] == 0:
//               key.append(alice_results[i])
//       return key
