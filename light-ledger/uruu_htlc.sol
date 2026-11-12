// SPDX-License-Identifier: MIT
// UruuHTLC — the URUU leg of an EXCAL <-> URUU quantum atomic swap.
//
// The EXCAL leg is a fork QHTLC lock (0x04 + hash160(descriptor),
// txscript.py lock_qhtlc): hash-locked by sha256(secret), claimable by
// the taker's Trifold root, refundable by the maker's Trifold root
// after the fork timeout. This contract is the mirror leg on zkSync
// Era: URUU locked by the SAME sha256(secret), claimable by the same
// counterparty, refundable after the zkSync timelock.
//
// Both legs share one secret, so whoever reveals it to claim one leg
// reveals it to the other — atomicity by hash, not by trust. The hash
// lock is SHA-256 (256-bit; Grover halves it to ~128-bit post-quantum
// security), and the EXCAL side uses hash-only Trifold signatures, so
// no ECDSA key appears anywhere in the swap. That is the quantum part:
// BTC-style swaps lean on secp256k1 signatures on both legs; this one
// leans on hashes on both legs.
//
// Timelock ordering (the safe direction): the URUU leg's timelock must
// expire AFTER the EXCAL leg's timeout, so the EXCAL maker can always
// refund first if the taker stalls. The wallet enforces this when it
// builds the offer (see the wallet build); the contract only enforces
// its own timelock.
//
// URUU: 0x5B6C9d85465Cc6FFe84039183872239657D90208 (zkSync Era, 18 dec).
//
// NOT DEPLOYED. Deployment needs Lux's deployer key + ETH for gas.

pragma solidity ^0.8.20;

interface IERC20 {
    function transferFrom(address from, address to, uint256 amount)
        external returns (bool);
    function transfer(address to, uint256 amount) external returns (bool);
}

contract UruuHTLC {
    IERC20 public immutable uruu;

    struct Lock {
        address locker;
        address claimer;
        uint256 amount;
        bytes32 hashlock;   // sha256(secret)
        uint256 timelock;   // unix seconds; refund at/after this
        bool spent;
    }

    mapping(bytes32 => Lock) public locks;

    event Locked(bytes32 indexed id, address indexed locker,
        address indexed claimer, uint256 amount, bytes32 hashlock,
        uint256 timelock);
    event Claimed(bytes32 indexed id, address indexed claimer,
        bytes32 secret);
    event Refunded(bytes32 indexed id, address indexed locker);

    constructor(address _uruu) {
        uruu = IERC20(_uruu);
    }

    function lock(
        bytes32 id, address claimer, uint256 amount,
        bytes32 hashlock, uint256 timelock
    ) external {
        require(locks[id].locker == address(0), "lock id in use");
        require(claimer != address(0), "zero claimer");
        require(amount > 0, "zero amount");
        require(timelock > block.timestamp, "timelock in the past");
        require(uruu.transferFrom(msg.sender, address(this), amount),
            "URUU transfer failed");
        locks[id] = Lock({
            locker: msg.sender, claimer: claimer, amount: amount,
            hashlock: hashlock, timelock: timelock, spent: false
        });
        emit Locked(id, msg.sender, claimer, amount, hashlock, timelock);
    }

    function claim(bytes32 id, bytes32 secret) external {
        Lock storage l = locks[id];
        require(l.locker != address(0), "unknown lock");
        require(!l.spent, "already spent");
        require(msg.sender == l.claimer, "only the claimer");
        require(sha256(abi.encodePacked(secret)) == l.hashlock,
            "wrong secret");
        require(block.timestamp < l.timelock, "timelock expired");
        l.spent = true;
        require(uruu.transfer(l.claimer, l.amount), "URUU payout failed");
        emit Claimed(id, l.claimer, secret);
    }

    function refund(bytes32 id) external {
        Lock storage l = locks[id];
        require(l.locker != address(0), "unknown lock");
        require(!l.spent, "already spent");
        require(msg.sender == l.locker, "only the locker");
        require(block.timestamp >= l.timelock, "timelock not reached");
        l.spent = true;
        require(uruu.transfer(l.locker, l.amount), "URUU refund failed");
        emit Refunded(id, l.locker);
    }
}
