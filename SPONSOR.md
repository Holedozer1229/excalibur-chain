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

1. Pick an unmined height (check the current tip in
   `genealogy_checkpoint.json`; heights are first-come-first-served).
2. Pay the price for that height in BTC to
   `12jgGaSXJ7jQvrroNZYru13CrjEaZrmDPj`, with your chosen PKH lock
   (42-char lock hex or 40-char hash160) and your tag (≤ 60 bytes of
   text) communicated alongside the payment.
3. Your (height → lock, tag) entry goes into the shim's sponsor
   registry. When the chain reaches your height, the coinbase is
   built to your lock with your tag in the scriptSig — regardless of
   who mines the block.
4. Verify delivery yourself: run the verifier, read your block's
   coinbase. The 50 EXCAL subsidy in that block is yours (it pays
   your lock; spendable under the chain's normal rules, 100-block
   coinbase maturity).

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
