# POWDER LOTS — crowdfund the Dr. Time finale

Three broadcasts are built, self-tested, and armed to be written into
Bitcoin forever:

1. **AETHER/v2 — the Declaration.** The capsule commitment
   (sha256 `d0173ec2…bcf8c4b1`, anchored on the Excalibur fork since
   block 23,674) sealed into a mainnet OP_RETURN.
2. **The 1A1z Tribute.** The same capsule, plus a 546-sat output paid
   to the genesis address `1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa` —
   speaking *to* the first address, from a chain that descends from it.
3. **QDAY/v1 — the Countersignature.** A hash-only post-quantum
   (Trifold) signature over the byte-exact Bitcoin genesis header,
   its root and bundle hash carried on mainnet.

The only missing ingredient is powder: each broadcast spends from the
dedicated Aether Genesis Key, and it has never been funded.

## Buy a lot — your sats fire the act

Send ONE lot's worth of BTC to the genesis key:

**`bc1q9c8cncqhmj9laecfm05x77d0c7dtcdhmemlwp7`**

| Lot | Act | Price (at 1 sat/vB) |
|-----|-----|---------------------|
| 1 | AETHER/v2 — the Declaration | ≥ 1,203 sats |
| 2 | The 1A1z Tribute (incl. the 546-sat tribute) | ≥ 1,783 sats |
| 3 | QDAY/v1 — the Countersignature | ≥ 1,205 sats |

Fees float; the watcher sizes lots at live fee rates, so a small
cushion (~10%) keeps your lot fireable on a fee spike. Send from a
wallet that lets you add an **OP_RETURN** to claim your lot by name:

- `POWDER1 <your name>` — Lot 1
- `POWDER2 <your name>` — Lot 2
- `POWDER3 <your name>` — Lot 3

Plain sends with no OP_RETURN become general powder and are just as
welcome.

## What happens then — no hands touch it

An autopilot watcher (`finale_watcher.py`) polls the address every
minute. When your lot lands:

- Your exact UTXO is reserved for your chosen act — it is never mixed
  or split. (Untagged lump sums big enough for all three acts are
  split into lots automatically.)
- The act fires on your sats. The broadcast transaction spends *your*
  UTXO, and the funding-txid → broadcast-txid pair is recorded in the
  public patrons ledger (`finale_patrons.md`) — a proof chain anyone
  can verify on any block explorer.
- Your name joins the finale certificate and the patrons ledger
  permanently.

Honest terms, same as everywhere in this repo: excess over the lot
price is not refunded — change returns to the project payout address
and funds the next act. EXCAL has no market and no return is promised
on anything here. What a lot buys is real and checkable: your powder
fires a specific, named, permanent broadcast — and the receipt is
written into Bitcoin itself.

One lump of ~6,200 sats or more fires the whole trilogy in order:
Declaration → Tribute → Countersignature.
