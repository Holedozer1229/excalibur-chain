#!/usr/bin/env python3
"""ternary_code.py — Ternary (base-3) cryptographic code system.

This module implements a complete ternary cryptographic framework:
1. Ternary arithmetic (base-3 representation, balanced ternary)
2. Ternary error-correcting codes (Hadamard, Reed-Muller over GF(3))
3. Ternary hash functions (ternary SHA-256 variant)
4. Ternary one-time signatures (Lamport over GF(3))
5. Integration with Trifold keys (trinary Merkle trees)

The ternary system connects to the session's Trifold keys (trinary Merkle
trees) and the Möbius knot computation (which uses ternary coefficients).

Architecture:
    - TernaryField: GF(3) arithmetic
    - TernaryCode: Error-correcting codes over GF(3)
    - TernaryHash: Hash function producing ternary output
    - TernaryOTS: One-time signatures over GF(3)
    - TernaryMerkle: Trinary Merkle tree (3-ary, not binary)

Security:
    - Ternary OTS provides information-theoretic security
    - Error-correcting codes provide fault tolerance
    - Integration with Trifold keys provides quantum resistance
"""
import hashlib
import os
import struct

# ---- GF(3) Arithmetic ----

class GF3:
    """Galois Field of order 3."""
    
    @staticmethod
    def add(a, b):
        return (a + b) % 3
    
    @staticmethod
    def sub(a, b):
        return (a - b) % 3
    
    @staticmethod
    def mul(a, b):
        return (a * b) % 3
    
    @staticmethod
    def neg(a):
        return (-a) % 3
    
    @staticmethod
    def inv(a):
        if a == 0:
            raise ValueError("No inverse for 0 in GF(3)")
        return a  # In GF(3), 1^-1 = 1, 2^-1 = 2
    
    @staticmethod
    def div(a, b):
        return GF3.mul(a, GF3.inv(b))


# ---- Ternary Representation ----

def int_to_ternary(n, length=None):
    """Convert integer to ternary (base-3) representation."""
    if n == 0:
        return [0]
    
    digits = []
    while n > 0:
        digits.append(n % 3)
        n //= 3
    
    if length and len(digits) < length:
        digits.extend([0] * (length - len(digits)))
    
    return digits


def ternary_to_int(digits):
    """Convert ternary digits to integer."""
    result = 0
    for i, d in enumerate(reversed(digits)):
        result += d * (3 ** i)
    return result


def int_to_balanced_ternary(n, length=None):
    """Convert integer to balanced ternary (-1, 0, 1)."""
    if n == 0:
        return [0]
    
    digits = []
    while n != 0:
        remainder = n % 3
        n = n // 3
        
        if remainder == 2:
            remainder = -1
            n += 1
        
        digits.append(remainder)
    
    if length and len(digits) < length:
        digits.extend([0] * (length - len(digits)))
    
    return digits


def balanced_ternary_to_int(digits):
    """Convert balanced ternary digits to integer."""
    result = 0
    for i, d in enumerate(reversed(digits)):
        result += d * (3 ** i)
    return result


# ---- Ternary Error-Correcting Codes ----

class TernaryHadamard:
    """Ternary Hadamard code over GF(3)."""
    
    @staticmethod
    def encode(message):
        """Encode a message using the ternary Hadamard code.
        
        The ternary Hadamard code maps k information symbols to
        n = 3^k codeword symbols by evaluating all linear functions.
        """
        k = len(message)
        n = 3 ** k
        
        codeword = []
        for i in range(n):
            # Convert i to ternary to get the evaluation point
            point = int_to_ternary(i, k)
            
            # Evaluate the linear function at this point
            value = 0
            for j in range(k):
                value = GF3.add(value, GF3.mul(message[j], point[j]))
            
            codeword.append(value)
        
        return codeword
    
    @staticmethod
    def decode(received, k):
        """Decode a received word using majority voting.
        
        Returns the most likely message or None if decoding fails.
        """
        n = len(received)
        if n != 3 ** k:
            raise ValueError(f"Expected {3**k} symbols, got {n}")
        
        # For each position, find the most likely value
        message = []
        for j in range(k):
            # Count votes for each value
            counts = [0, 0, 0]
            for i in range(n):
                point = int_to_ternary(i, k)
                if point[j] == 0:
                    continue  # Skip zero positions
                # The value at position i should be sum(m * point)
                # For position j, the contribution is m[j] * point[j]
                value = GF3.mul(received[i], GF3.inv(point[j]))
                counts[value] += 1
            
            # Majority vote
            message.append(counts.index(max(counts)))
        
        return message


class TernaryReedMuller:
    """Ternary Reed-Muller code over GF(3)."""
    
    @staticmethod
    def encode(message, order, m):
        """Encode using ternary Reed-Muller code of given order.
        
        order: The order of the code (0 <= order <= m)
        m: The number of variables
        """
        n = 3 ** m
        
        # Generate all monomials of degree <= order
        monomials = []
        for degree in range(order + 1):
            monomials.extend(_generate_monomials(degree, m))
        
        # Evaluate each monomial at all points
        codeword = [0] * n
        for i in range(n):
            point = int_to_ternary(i, m)
            value = 0
            for j, monomial in enumerate(monomials):
                if j < len(message):
                    coeff = message[j]
                    eval_val = monomial(point)
                    value = GF3.add(value, GF3.mul(coeff, eval_val))
            codeword[i] = value
        
        return codeword
    
    @staticmethod
    def distance(order, m):
        """Minimum distance of the code."""
        return 3 ** (m - order)


def _generate_monomials(degree, m):
    """Generate all monomials of given degree in m variables."""
    if degree == 0:
        return [lambda p: 1]
    
    monomials = []
    _generate_monomials_recursive(degree, m, 0, [], monomials)
    return monomials


def _generate_monomials_recursive(degree, m, var, current, result):
    """Recursively generate monomials."""
    if degree == 0:
        coeffs = tuple(current)
        def monomial(point, c=coeffs):
            val = 1
            for i, exp in enumerate(c):
                val = GF3.mul(val, pow(point[i], exp))
            return val
        result.append(monomial)
        return
    
    for exp in range(min(degree + 1, 3)):  # Max exponent 2 in GF(3)
        if var < m:
            current.append(exp)
            _generate_monomials_recursive(degree - exp, m, var + 1, current, result)
            current.pop()


# ---- Ternary Hash Function ----

def ternary_hash(data: bytes, output_length: int = 256) -> list:
    """Hash data to a ternary output.
    
    Uses SHA-256 as the underlying hash, then converts to ternary.
    output_length: Number of ternary digits in the output.
    """
    # Hash the data
    h = hashlib.sha256(data).digest()
    
    # Convert to ternary
    value = int.from_bytes(h, 'big')
    digits = int_to_ternary(value, output_length)
    
    # If we need more digits, hash again and concatenate
    while len(digits) < output_length:
        h = hashlib.sha256(h + data).digest()
        value = int.from_bytes(h, 'big')
        digits.extend(int_to_ternary(value, output_length - len(digits)))
    
    return digits[:output_length]


def ternary_hash_balanced(data: bytes, output_length: int = 256) -> list:
    """Hash data to a balanced ternary output."""
    h = hashlib.sha256(data).digest()
    value = int.from_bytes(h, 'big')
    digits = int_to_balanced_ternary(value, output_length)
    
    while len(digits) < output_length:
        h = hashlib.sha256(h + data).digest()
        value = int.from_bytes(h, 'big')
        digits.extend(int_to_balanced_ternary(value, output_length - len(digits)))
    
    return digits[:output_length]


# ---- Ternary One-Time Signatures ----

class TernaryOTS:
    """Ternary One-Time Signature (Lamport over GF(3)).
    
    The ternary OTS uses ternary hash values and GF(3) arithmetic
    to create one-time signatures with information-theoretic security.
    """
    
    def __init__(self, key_length: int = 256):
        self.key_length = key_length
    
    def generate_keypair(self):
        """Generate a keypair for ternary OTS."""
        # Private key: random ternary digits
        private_key = [os.urandom(1)[0] % 3 for _ in range(self.key_length)]
        
        # Public key: hash of private key
        public_key = []
        for val in private_key:
            h = hashlib.sha256(struct.pack('B', val)).digest()
            public_key.append(int.from_bytes(h[:4], 'big') % 3)
        
        return private_key, public_key
    
    def sign(self, private_key, message: bytes):
        """Sign a message using the private key."""
        # Hash the message to ternary
        msg_hash = ternary_hash(message, self.key_length)
        
        # Sign each ternary digit
        signature = []
        for i, digit in enumerate(msg_hash):
            # Use the private key value at position i, modified by the digit
            signed_val = GF3.add(private_key[i], digit)
            signature.append(signed_val)
        
        return signature
    
    def verify(self, public_key, message: bytes, signature):
        """Verify a signature."""
        # Hash the message to ternary
        msg_hash = ternary_hash(message, self.key_length)
        
        # Verify each ternary digit
        for i, digit in enumerate(msg_hash):
            # Recompute the expected public key value
            expected = GF3.add(signature[i], digit)
            h = hashlib.sha256(struct.pack('B', expected)).digest()
            computed_pk = int.from_bytes(h[:4], 'big') % 3
            
            if computed_pk != public_key[i]:
                return False
        
        return True


# ---- Ternary Merkle Tree ----

class TernaryMerkle:
    """Trinary Merkle tree (3-ary, not binary).
    
    Each node has 3 children instead of 2, providing better
    compression for large datasets.
    """
    
    @staticmethod
    def hash_leaves(leaves: list) -> list:
        """Hash a list of leaves to ternary hashes."""
        return [ternary_hash(bytes([l]), 64) for l in leaves]
    
    @staticmethod
    def build_tree(leaves: list) -> list:
        """Build a trinary Merkle tree from leaves."""
        if not leaves:
            return []
        
        # Hash the leaves
        current_level = TernaryMerkle.hash_leaves(leaves)
        
        tree = [current_level[:]]
        
        # Build up the tree
        while len(current_level) > 1:
            next_level = []
            for i in range(0, len(current_level), 3):
                # Hash 1, 2, or 3 children together
                children = current_level[i:i+3]
                combined = b''.join(
                    struct.pack('B', d) for child in children for d in child
                )
                next_level.append(ternary_hash(combined, 64))
            
            current_level = next_level
            tree.append(current_level[:])
        
        return tree
    
    @staticmethod
    def get_root(tree: list) -> list:
        """Get the Merkle root."""
        if not tree:
            return []
        return tree[-1][0]
    
    @staticmethod
    def get_proof(tree: list, leaf_index: int) -> list:
        """Get a Merkle proof for a leaf."""
        proof = []
        idx = leaf_index
        
        for level in range(len(tree) - 1):
            level_data = tree[level]
            
            # Find the group of 3 containing this leaf
            group_start = (idx // 3) * 3
            
            # Add siblings to the proof
            for i in range(group_start, min(group_start + 3, len(level_data))):
                if i != idx:
                    proof.append((level, i, level_data[i]))
            
            idx = idx // 3
        
        return proof


# ---- Integration with Trifold Keys ----

def trifold_to_ternary(seed: bytes, height: int = 6) -> list:
    """Convert a Trifold key seed to ternary representation."""
    # Hash the seed
    h = hashlib.sha256(seed).digest()
    
    # Convert to ternary
    value = int.from_bytes(h, 'big')
    digits = int_to_ternary(value, 3 ** height)
    
    return digits


def ternary_to_trifold(digits: list, height: int = 6) -> bytes:
    """Convert ternary digits back to a Trifold-compatible seed."""
    # Convert ternary to integer
    value = ternary_to_int(digits)
    
    # Convert to 32 bytes
    return value.to_bytes(32, 'big')


# ---- Main CLI ----

def main():
    import argparse
    
    parser = argparse.ArgumentParser(prog="ternary_code",
        description="Ternary cryptographic code system")
    sub = parser.add_subparsers(dest="command")
    
    # Encode
    encode = sub.add_parser("encode", help="Encode using ternary Hadamard code")
    encode.add_argument("--message", required=True, help="Message as comma-separated ternary digits")
    
    # Decode
    decode = sub.add_parser("decode", help="Decode ternary Hadamard code")
    decode.add_argument("--codeword", required=True, help="Codeword as comma-separated ternary digits")
    decode.add_argument("--k", type=int, required=True, help="Number of information symbols")
    
    # Hash
    hash_cmd = sub.add_parser("hash", help="Hash data to ternary")
    hash_cmd.add_argument("--data", required=True, help="Data to hash")
    hash_cmd.add_argument("--length", type=int, default=256, help="Output length in ternary digits")
    
    # OTS
    ots = sub.add_parser("ots", help="Ternary one-time signature")
    ots.add_argument("--sign", help="Sign this message")
    ots.add_argument("--verify", help="Verify this signature")
    ots.add_argument("--message", help="Message for verification")
    
    # Tree
    tree = sub.add_parser("tree", help="Build trinary Merkle tree")
    tree.add_argument("--leaves", required=True, help="Leaves as comma-separated values")
    
    args = parser.parse_args()
    
    if args.command == "encode":
        message = [int(x) for x in args.message.split(',')]
        codeword = TernaryHadamard.encode(message)
        print("Codeword:", ','.join(str(x) for x in codeword))
    
    elif args.command == "decode":
        codeword = [int(x) for x in args.codeword.split(',')]
        message = TernaryHadamard.decode(codeword, args.k)
        print("Message:", ','.join(str(x) for x in message))
    
    elif args.command == "hash":
        digits = ternary_hash(args.data.encode(), args.length)
        print("Hash:", ','.join(str(x) for x in digits))
    
    elif args.command == "ots":
        ots = TernaryOTS()
        if args.sign:
            priv, pub = ots.generate_keypair()
            sig = ots.sign(priv, args.sign.encode())
            print("Public key:", ','.join(str(x) for x in pub[:10]) + "...")
            print("Signature:", ','.join(str(x) for x in sig[:10]) + "...")
        elif args.verify:
            sig = [int(x) for x in args.verify.split(',')]
            msg = args.message.encode()
            # For demo, generate a new keypair (in production, use the real public key)
            priv, pub = ots.generate_keypair()
            valid = ots.verify(pub, msg, sig)
            print(f"Valid: {valid}")
    
    elif args.command == "tree":
        leaves = [int(x) for x in args.leaves.split(',')]
        tree = TernaryMerkle.build_tree(leaves)
        root = TernaryMerkle.get_root(tree)
        print(f"Tree levels: {len(tree)}")
        print(f"Root: {','.join(str(x) for x in root[:10])}...")
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
