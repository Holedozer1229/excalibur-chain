#!/usr/bin/env python3
"""
Test to verify the corrected tau(28) value and Ramanujan congruence.

The key finding: tau(28) = -703236000 was WRONG.
The correct value is tau(28) = tau(4) * tau(7) = -1472 * -16744 = 24,647,168
(because tau is multiplicative and gcd(4,7) = 1).

With the correct value, the famous Ramanujan congruence
tau(n) = sigma_11(n) mod 691 holds for ALL n, including n=28.
"""

import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestRamanujanCongruence(unittest.TestCase):
    """Verify the Ramanujan congruence tau(n) = sigma_11(n) mod 691."""

    def sigma_11(self, n):
        """Sum of 11th powers of divisors of n."""
        s = 0
        for d in range(1, n + 1):
            if n % d == 0:
                s += d ** 11
        return s

    def test_tau_28_correct_value(self):
        """tau(28) = tau(4) * tau(7) = -1472 * -16744 = 24647168."""
        tau_4 = -1472
        tau_7 = -16744
        tau_28 = tau_4 * tau_7
        self.assertEqual(tau_28, 24647168)

    def test_tau_28_wrong_value(self):
        """The old value -703236000 is NOT tau(28)."""
        tau_4 = -1472
        tau_7 = -16744
        tau_28 = tau_4 * tau_7
        self.assertNotEqual(tau_28, -703236000)

    def test_ramanujan_congruence_n28(self):
        """tau(28) = sigma_11(28) mod 691 — the famous Ramanujan congruence."""
        tau_28 = 24647168
        s11_28 = self.sigma_11(28)
        self.assertEqual(tau_28 % 691, s11_28 % 691)
        self.assertEqual(tau_28 % 691, 580)
        self.assertEqual(s11_28 % 691, 580)

    def test_ramanujan_congruence_wrong_value_fails(self):
        """The wrong tau(28) = -703236000 breaks the congruence."""
        wrong_tau_28 = -703236000
        s11_28 = self.sigma_11(28)
        self.assertNotEqual(wrong_tau_28 % 691, s11_28 % 691)
        self.assertEqual(wrong_tau_28 % 691, 228)  # Wrong!
        self.assertEqual(s11_28 % 691, 580)

    def test_ramanujan_congruence_verified_n(self):
        """Verify the congruence holds for n where tau values are confirmed correct.
        
        The tau values for n=13..27 in the codebase are incorrect.
        Only n=1..12 and n=28 (corrected) have verified tau values.
        """
        # Verified correct tau values
        tau_verified = {
            1: 1, 2: -24, 3: 252, 4: -1472, 5: 4830, 6: -6048, 7: -16744,
            8: 84480, 9: -113643, 10: -115920, 11: 534612, 12: -370944,
            28: 24647168,  # CORRECTED from -703236000
        }

        for n, tau_n in tau_verified.items():
            s11_n = self.sigma_11(n)
            self.assertEqual(
                tau_n % 691, s11_n % 691,
                f"Congruence fails at n={n}: tau={tau_n % 691}, sigma_11={s11_n % 691}"
            )

    def test_tau_multiplicative_property(self):
        """tau is multiplicative: tau(mn) = tau(m)*tau(n) when gcd(m,n)=1."""
        # 28 = 4 * 7, gcd(4,7) = 1
        tau_4 = -1472
        tau_7 = -16744
        tau_28 = tau_4 * tau_7
        self.assertEqual(tau_28, 24647168)

        # 6 = 2 * 3, gcd(2,3) = 1
        tau_2 = -24
        tau_3 = 252
        tau_6 = tau_2 * tau_3
        self.assertEqual(tau_6, -6048)

        # 10 = 2 * 5, gcd(2,5) = 1
        tau_2 = -24
        tau_5 = 4830
        tau_10 = tau_2 * tau_5
        self.assertEqual(tau_10, -115920)

    def test_sigma_11_28_value(self):
        """sigma_11(28) = 8,297,561,014,164,632."""
        s11_28 = self.sigma_11(28)
        self.assertEqual(s11_28, 8297561014164632)

    def test_codebase_tau_28_constant(self):
        """Verify the codebase constant TAU_28 is set to the correct value."""
        from canonical_proof_of_control import TAU_28
        self.assertEqual(TAU_28, 24647168)


if __name__ == '__main__':
    unittest.main(verbosity=2)
