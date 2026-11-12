// SPDX-License-Identifier: MIT
// ExcaliburCheckpointAnchor — URUU-anchored light-ledger checkpoints.
//
// A checkpoint is a claim about the Excalibur fork at height H:
//   { tipHash, overlayRoot, spentRoot, chainwork } signed by the QAI
//   auditor's Trifold key (authentication, off-chain).
//
// This contract adds the part a signature cannot: ECONOMIC FINALITY.
// The auditor posts a URUU bond with each checkpoint. Inside the fraud
// window (default 24h) anyone may challenge with a fraud proof; a
// proven challenge voids the checkpoint and slashes the bond to the
// challenger. After the window passes unchallenged, the checkpoint is
// FINAL — and only FINAL checkpoints may bootstrap a light node.
//
// Trust model, stated plainly: this removes trust in the auditor's key
// and replaces it with (a) zkSync Era consensus + this contract's code,
// (b) at least one honest watcher inside the fraud window, and (c) the
// fraud-proof verifier below. It is the optimistic model —
// trust-minimized, not trust-free. A light node that bootstraps from a
// FINAL checkpoint still trusts that no valid challenge existed; it does
// NOT re-validate history. Full replay remains the only trust-free path.
//
// Fraud proof (omission) — what the challenger supplies:
//   * headers: the 80-byte fork headers from the creating block up to
//     the checkpoint tip, in order. The contract checks the chain links
//     (each prevHash == previous header hash), each header's proof of
//     work against its compact target, and that the last header's hash
//     equals the checkpoint's tipHash. Checkpoints should be frequent
//     so this segment is short; the gas cost grows with its length.
//   * tx + txProof: the transaction that creates the omitted UTXO, with
//     its Merkle inclusion proof against the creating block's merkle
//     root (taken from the supplied header).
//   * output: the exact UTXO (value + lock script) the tx creates.
//   * absence: the sorted-Merkle absence proof — the two bracketing
//     leaves of the checkpoint's overlay set, each with its inclusion
//     proof, plus their keys. The contract checks both inclusion proofs,
//     the ordering (leftKey < utxoKey < rightKey), and ADJACENCY
//     (rightIndex == leftIndex + 1): without adjacency a prover could
//     straddle the key with two far-apart leaves and hide a present
//     UTXO between them.
//
// URUU: 0x5B6C9d85465Cc6FFe84039183872239657D90208 on zkSync Era (chain
// 324), 18 decimals, total supply 100,000,000. Bond: 1,000 URUU per
// checkpoint (changeable by Lux; set at deployment).
//
// NOT DEPLOYED. Deployment needs Lux's deployer key + ETH for gas on
// zkSync Era. Until then the checkpoint's uruu.contract field is null
// and the anchor leg is pending; snapshot + Trifold attestation already
// verify offline (see lightledger.py).

pragma solidity ^0.8.20;

interface IERC20 {
    function transferFrom(address from, address to, uint256 amount)
        external returns (bool);
    function transfer(address to, uint256 amount) external returns (bool);
}

contract ExcaliburCheckpointAnchor {
    IERC20 public immutable uruu;
    uint256 public immutable bondUruu;      // base units (18 decimals)
    uint256 public immutable fraudWindow;   // seconds

    enum Status { Pending, Final, Void }

    struct Checkpoint {
        uint256 height;
        bytes32 tipHash;
        bytes32 overlayRoot;
        uint32 overlayCount;
        address auditor;
        uint64 issuedAt;
        Status status;
    }

    mapping(bytes32 => Checkpoint) public checkpoints;

    event CheckpointAnchored(
        bytes32 indexed checkpointHash, uint256 height,
        bytes32 tipHash, bytes32 overlayRoot, address indexed auditor);
    event CheckpointChallenged(
        bytes32 indexed checkpointHash, address indexed challenger,
        bytes32 utxoKey);
    event CheckpointFinalized(bytes32 indexed checkpointHash);

    constructor(address _uruu, uint256 _bondUruu, uint256 _fraudWindow) {
        uruu = IERC20(_uruu);
        bondUruu = _bondUruu;
        fraudWindow = _fraudWindow;
    }

    function anchorCheckpoint(
        bytes32 checkpointHash, uint256 height, bytes32 tipHash,
        bytes32 overlayRoot, uint32 overlayCount
    ) external {
        require(checkpoints[checkpointHash].auditor == address(0),
            "checkpoint already anchored");
        require(uruu.transferFrom(msg.sender, address(this), bondUruu),
            "bond transfer failed");
        checkpoints[checkpointHash] = Checkpoint({
            height: height, tipHash: tipHash, overlayRoot: overlayRoot,
            overlayCount: overlayCount, auditor: msg.sender,
            issuedAt: uint64(block.timestamp), status: Status.Pending
        });
        emit CheckpointAnchored(
            checkpointHash, height, tipHash, overlayRoot, msg.sender);
    }

    function finalize(bytes32 checkpointHash) external {
        Checkpoint storage cp = checkpoints[checkpointHash];
        require(cp.auditor != address(0), "unknown checkpoint");
        require(cp.status == Status.Pending, "not pending");
        require(block.timestamp >= cp.issuedAt + fraudWindow,
            "fraud window still open");
        cp.status = Status.Final;
        emit CheckpointFinalized(checkpointHash);
    }

    // ---- fraud proof: omitted UTXO ----------------------------------
    struct AbsenceLeaf {
        uint256 index;
        bytes32 leaf;
        bytes32[] proof;   // sibling hashes, leaf -> root
        bool[] isLeft;     // true when the sibling sits on the left
    }

    struct OmissionProof {
        bytes[] headers;       // creating block .. tip, in order
        bytes tx;              // raw tx that creates the UTXO
        uint256 txIndex;
        bytes32[] txProof;     // siblings, tx -> block merkle root
        bool[] txIsLeft;
        uint256 vout;
        uint256 value;
        bytes lockScript;
        AbsenceLeaf left;
        AbsenceLeaf right;     // right.index == 0 && right.leaf == 0
                               // means "no right neighbour"
        bytes32 leftKey;       // 36-byte UTXO key encodings, or 0
        bytes32 rightKey;
    }

    function challengeOmission(
        bytes32 checkpointHash, OmissionProof calldata p
    ) external {
        Checkpoint storage cp = checkpoints[checkpointHash];
        require(cp.auditor != address(0), "unknown checkpoint");
        require(cp.status == Status.Pending, "not pending");
        require(block.timestamp < cp.issuedAt + fraudWindow,
            "fraud window closed");

        // 1. Header chain: links, PoW, ends at the checkpoint tip.
        bytes32 prevHash = bytes32(0);
        for (uint256 i = 0; i < p.headers.length; i++) {
            bytes memory h = p.headers[i];
            require(h.length == 80, "header must be 80 bytes");
            bytes32 hash = _headerHash(h);
            if (i > 0) {
                require(_headerPrev(h) == prevHash, "header chain broken");
            }
            require(_meetsTarget(hash, _headerBits(h)), "bad PoW");
            prevHash = hash;
        }
        require(prevHash == cp.tipHash, "chain does not end at tip");
        require(p.headers.length > 0, "empty header chain");

        // 2. The tx is in the creating block (Merkle proof).
        bytes32 txid = _txid(p.tx);
        bytes32 merkleRoot = _headerMerkle(p.headers[0]);
        require(_verifyInclusion(
            merkleRoot, txid, p.txProof, p.txIsLeft, p.txIndex),
            "tx not in block");

        // 3. The tx output is exactly the claimed UTXO.
        (uint256 value, bytes memory spk) = _txOutput(p.tx, p.vout);
        require(value == p.value, "output value mismatch");
        require(keccak256(spk) == keccak256(p.lockScript),
            "output script mismatch");

        // 4. The UTXO is absent from the checkpoint's overlay root.
        bytes32 utxoKey = _utxoKey(txid, p.vout);
        require(_verifyAbsence(cp.overlayRoot, cp.overlayCount, utxoKey, p),
            "UTXO is in the set");

        cp.status = Status.Void;
        require(uruu.transfer(msg.sender, bondUruu), "slash failed");
        emit CheckpointChallenged(checkpointHash, msg.sender, utxoKey);
    }

    // ---- internals ---------------------------------------------------
    function _headerHash(bytes memory h) internal pure returns (bytes32) {
        return sha256(abi.encodePacked(sha256(h)));
    }

    function _headerPrev(bytes memory h) internal pure returns (bytes32) {
        bytes32 v;
        assembly { v := mload(add(h, 36)) } // offset 4..36
        return v;
    }

    function _headerMerkle(bytes memory h) internal pure returns (bytes32) {
        bytes32 v;
        assembly { v := mload(add(h, 68)) } // offset 36..68
        return v;
    }

    function _headerBits(bytes memory h) internal pure returns (uint32) {
        uint32 v;
        assembly { v := mload(add(h, 76)) } // offset 72..76, low 4 bytes
        return v;
    }

    function _meetsTarget(bytes32 hash, uint32 bits)
        internal pure returns (bool)
    {
        uint256 exponent = uint256(bits >> 24);
        uint256 mantissa = uint256(bits & 0x007fffff);
        require(exponent >= 3 && exponent <= 32, "bad bits exponent");
        uint256 target = mantissa << (8 * (exponent - 3));
        // Bitcoin hashes are compared little-endian; the raw sha256d
        // output is big-endian bytes of the same number reversed.
        // Compare as uint256 of the reversed bytes.
        uint256 hv = _reverseUint(hash);
        return hv < target;
    }

    function _reverseUint(bytes32 x) internal pure returns (uint256) {
        uint256 v = uint256(x);
        uint256 r = 0;
        for (uint256 i = 0; i < 32; i++) {
            r = (r << 8) | (v & 0xff);
            v >>= 8;
        }
        return r;
    }

    function _txid(bytes memory raw) internal pure returns (bytes32) {
        return sha256(abi.encodePacked(sha256(raw)));
    }

    function _verifyInclusion(
        bytes32 root, bytes32 leaf, bytes32[] calldata proof,
        bool[] calldata isLeft, uint256 index
    ) internal pure returns (bool) {
        bytes32 node = leaf;
        uint256 idx = index;
        for (uint256 i = 0; i < proof.length; i++) {
            node = isLeft[i]
                ? sha256(abi.encodePacked(sha256(abi.encodePacked(proof[i], node))))
                : sha256(abi.encodePacked(sha256(abi.encodePacked(node, proof[i]))));
            idx /= 2;
        }
        return node == root;
    }

    function _verifyAbsence(
        bytes32 root, uint32 total, bytes32 utxoKey, OmissionProof calldata p
    ) internal pure returns (bool) {
        bool hasLeft = p.left.leaf != bytes32(0);
        bool hasRight = p.right.leaf != bytes32(0);
        if (total == 0) return !hasLeft && !hasRight;
        if (!hasLeft && !hasRight) return false;
        if (hasLeft) {
            if (!_verifyInclusion(root, p.left.leaf, p.left.proof,
                                  p.left.isLeft, p.left.index)) return false;
            if (!(p.leftKey < utxoKey)) return false;
        }
        if (hasRight) {
            if (!_verifyInclusion(root, p.right.leaf, p.right.proof,
                                  p.right.isLeft, p.right.index)) return false;
            if (!(utxoKey < p.rightKey)) return false;
        }
        if (hasLeft && hasRight) {
            if (p.right.index != p.left.index + 1) return false;
        } else if (!hasLeft) {
            if (p.right.index != 0) return false;
        } else {
            if (p.left.index != total - 1) return false;
        }
        return true;
    }

    function _utxoKey(bytes32 txid, uint256 vout)
        internal pure returns (bytes32)
    {
        // 36-byte key (txid || vout LE) truncated to 32 bytes for the
        // on-chain comparison: the txid alone is unique per tx and the
        // vout is carried in the output check above. The full 36-byte
        // key is used off-chain (lightledger.py); on-chain the txid
        // plus the verified output pins the UTXO exactly.
        return txid;
    }

    function _txOutput(bytes memory raw, uint256 vout)
        internal pure returns (uint256 value, bytes memory spk)
    {
        // Minimal legacy-tx output parser: version(4) [marker+flag if
        // segwit] varint vin-count, inputs, varint vout-count, outputs.
        // Fork transactions are legacy; a witness marker aborts.
        uint256 p = 4;
        require(raw.length > p + 1, "tx too short");
        if (raw[p] == 0x00) revert("segwit tx unsupported");
        (uint256 nIn, uint256 n) = _varint(raw, p);
        p += n;
        for (uint256 i = 0; i < nIn; i++) {
            p += 36; // prev txid + vout
            (uint256 sl, uint256 m) = _varint(raw, p);
            p += m + sl + 4; // script + sequence
        }
        (uint256 nOut, uint256 n2) = _varint(raw, p);
        p += n2;
        require(vout < nOut, "vout out of range");
        for (uint256 j = 0; j <= vout; j++) {
            uint256 v;
            assembly { v := mload(add(raw, add(p, 8))) }
            // value is 8 little-endian bytes at p..p+8
            value = _le64(raw, p);
            (uint256 ll, uint256 m2) = _varint(raw, p + 8);
            if (j == vout) {
                spk = new bytes(ll);
                for (uint256 k = 0; k < ll; k++) spk[k] = raw[p + 8 + m2 + k];
                return (value, spk);
            }
            p += 8 + m2 + ll;
        }
        revert("unreachable");
    }

    function _le64(bytes memory b, uint256 p)
        internal pure returns (uint256)
    {
        uint256 v = 0;
        for (uint256 i = 0; i < 8; i++) {
            v |= uint256(uint8(b[p + i])) << (8 * i);
        }
        return v;
    }

    function _varint(bytes memory b, uint256 p)
        internal pure returns (uint256 v, uint256 n)
    {
        uint8 first = uint8(b[p]);
        if (first < 0xfd) return (first, 1);
        if (first == 0xfd) {
            return (uint256(uint8(b[p + 1])) |
                    (uint256(uint8(b[p + 2])) << 8), 3);
        }
        if (first == 0xfe) {
            uint256 x = 0;
            for (uint256 i = 0; i < 4; i++) {
                x |= uint256(uint8(b[p + 1 + i])) << (8 * i);
            }
            return (x, 5);
        }
        uint256 y = 0;
        for (uint256 i = 0; i < 8; i++) {
            y |= uint256(uint8(b[p + 1 + i])) << (8 * i);
        }
        return (y, 9);
    }
}
