# Sponsored blocks — own a height

A sponsored block is a block of the Excalibur fork whose coinbase pays
**your** lock and seals **your** message, delivered automatically by
the stratum shim when the chain reaches your height. Delivery needs no
trust: the block either carries your lock and tag or it doesn't, and
anyone can check with `genealogy_verify.py` in under ten seconds.

What you are buying is permanence with a pedigree: a position in a
chain anchored to Bitcoin block 968,698, whose lineage is
countersigned back to the Bitcoin genesis header by hash-only
(Trifold) signatures — sealed under proof-of-work that anyone can
audit. What you are **not** buying is an investment: EXCAL has no
market and no price today, and no return is promised or implied.

## How it works

Sales are open now. The payment watcher polls the payout address
every minute and writes valid paid orders into the sponsor registry
automatically after **one Bitcoin confirmation**.

1. Pick an unmined, unsold height safely in the future — at least
   10 blocks beyond the current tip in `genealogy_checkpoint.json`.
   Heights are first-come-first-served.
2. Pay at least the lot price in BTC to
   `12jgGaSXJ7jQvrroNZYru13CrjEaZrmDPj`.
3. Make the payment self-describing by adding one OP_RETURN output
   with this exact byte layout (80 bytes maximum):

   `"EXCAL1" | height: 3 bytes, big-endian | hash160: 20 bytes | tag: up to 51 bytes`

   The hash160 is the 20-byte hash of the public key that should
   receive the block's 50 EXCAL subsidy. The tag is UTF-8 text sealed
   in the coinbase.
4. If your wallet cannot add an OP_RETURN, pay the amount and open a
   GitHub issue in this repository containing only the transaction
   ID, chosen height, destination address or hash160, and tag. Never
   post a private key or seed phrase. A watcher files orderless
   payments for manual review instead of silently dropping them.
5. When the chain reaches your height, the coinbase is built to your
   lock with your tag in the scriptSig — regardless of who mines the
   block. Verify delivery yourself: run the verifier and read the
   block's coinbase. The 50 EXCAL subsidy is yours under the chain's
   normal rules, including 100-block coinbase maturity.

The watcher implementation is `payment_watcher.py`; its simulated
payment tests are in `test_watcher.py`.

## Opening schedule (BTC)

| Height class | Price |
|---|---|
| Any ordinary future height | 0.001 |
| Round heights (…27,000, 28,000, …) | 0.01 |
| The GPU-flood equilibration block (named when the rig connects) | 0.05 |
| Height 30,000 | 0.05 |

Prices are the opening schedule and may be repriced for unsold
heights at any time; a confirmed payment locks the price for that
height. During the GPU flood the chain produces ~600 blocks in about
ninety minutes — sprint-era heights are sold from the same registry
while they last.
