# 1,000 EXCAL, 1 EXCAL and 0.001 EXCAL for BTC — self-serve hash-locked swaps (no messaging)

**The offers:** 1,000 EXCAL for whatever BTC you offer — you name the price. 1 EXCAL for exactly 1 BTC (1:1). 0.001 EXCAL for exactly 0.001 BTC (1:1) — the micro pilot. Three lots, same flow — pick one with `--lot 1k` (the default), `--lot 1excal`, or `--lot pilot001`.

The 1,000 EXCAL lot is already committed: funding tx
`4873ebb3a40b83f2401266587aba9f73bf837dd51349e07029b06819fcccfc95`
is **confirmed on the Excalibur fork in block 42899** — exactly 1,000
EXCAL locked in a quantum-resistant QHTLC. The 1 EXCAL lot is committed
too: funding tx `449fb35dafc7dc8f40faca892845730725961840b0fb945fa8b88b4e902287f1`
is **confirmed on the Excalibur fork in block 42900** — exactly 1 EXCAL
locked. The 0.001 EXCAL pilot lot is committed too: funding tx
`6ee1f5da1aaa83c0652603a3f2f07018603b8d1d32b7fda26edfa500b0e1c439`
is **confirmed on the Excalibur fork in block 43571** — exactly 0.001
EXCAL locked. You can verify any lock on the fork chain yourself before
you fund anything.

EXCAL is the coin of the Excalibur fork — the first hard fork to rebuild Bitcoin’s locks from scratch: opcode-free and quantum-resistant.

**You do not have to message anyone.** Pick your amount (any amount for the 1,000 EXCAL lot; exactly 1 BTC for the 1 EXCAL lot; exactly 0.001 BTC for the pilot lot), build your funding
transaction with the script below, sign it in your own wallet, broadcast
it. The rest happens on-chain and in public. No DMs, no negotiation, no
waiting on a reply.

**Settlement model — read this first.** This is a hash-locked,
counterparty-dependent exchange, not a trustless atomic swap. The maker
claims your BTC first (which reveals the secret on-chain), and you must
then claim the EXCAL yourself using that secret plus the delivered claim
seed. If you never claim the EXCAL, your BTC is already gone and the
EXCAL refunds to the maker at the fork timeout. Claim promptly once the
secret appears.

## Public parameters (verify them yourself — do not trust this file alone)

Per lot, in `lots/1k.json`, `lots/1excal.json` and `lots/pilot001.json` (the scripts read them):

| Item | 1,000 EXCAL lot | 1 EXCAL lot | 0.001 EXCAL pilot lot |
|---|---|---|---|
| Funding txid | `4873ebb3…` (fork block 42899) | `449fb35d…` (fork block 42900) | `6ee1f5da…` (fork block 43571) |
| QHTLC lock | `04522033…` | `04584460…` | `04e1f59c…` |
| Secret hash (SHA256) | `d1baf924…` | `95d706ed…` | `59db7d74…` |
| Claim root | `91f33e7f…` | `1f4a1780…` | `1efd23e3…` |
| Refund root | `9471855e…` | `749c23e1…` | `66df77c5…` |
| EXCAL refund timeout | fork height 62898 | fork height 62899 | fork height 63557 |
| OP_RETURN tag | `EXCAL1K` | `EXCAL1` | `EXCALPILOT` |
| GitHub issue | #2 | #3 | #4 |

Shared: BTC claim key (Lux) `02e83113…`, BTC claim destination
`bc1qj37xg5qmyedwfe70cz0f385cxmf6642kcznjdg`, signal output 1,000 sats,
BTC HTLC timeout = the Bitcoin tip height when you build the funding
transaction + 144 blocks (~24h). The watcher verifies the actual refund
window against the confirmed funding height before delivering the claim
seed.

## How it works (4 steps, zero messages)

Get the kit: `git clone https://github.com/Holedozer1229/excalibur-chain.git`
— everything below lives in `self-serve/`.

**1. Fund your BTC HTLC — your lot's amount.**
Run `taker_htlc.py` (stdlib only, no keys leave your machine):
```
python3 taker_htlc.py --utxo TXID:VOUT --amount SATS \
    --refund-pubkey <your compressed pubkey hex> \
    --change-address <your bc1q change address> [--lot 1excal|pilot001]
```
It builds an unsigned PSBT for a funding tx with 4 outputs: your HTLC
(`amount` sats), an OP_RETURN carrying the lot's tag (`EXCAL1K` for the
1,000 EXCAL lot, `EXCAL1` for the 1 EXCAL lot, `EXCALPILOT` for the pilot
lot) + your fresh delivery
pubkey, the 1,000-sat signal, and your change. It also saves
`delivery_key.txt` — **keep that file**: it is the only way to decrypt
the claim seed. Sign the PSBT in your wallet (Sparrow / Electrum /
Bitcoin Core) and broadcast it. The script prints the expected txid —
check it matches after broadcast.
The script refuses to fund if a swap is already in progress (one lot,
one taker — first funded HTLC wins).

Then post your witness script hex (the script prints it) as a comment
on the lot's GitHub issue (#2 for the 1,000 EXCAL lot, #3 for 1 EXCAL,
#4 for the pilot lot), next to your
funding txid, so anyone can verify your HTLC. That is a public record,
not a message to anyone.

**2. The claim seed is delivered to you, encrypted.**
The swap watcher sees the 1,000-sat signal and verifies your HTLC
before delivering anything: the posted witness script must hash to the
funded P2WSH output, the funding transaction must be confirmed (6+
confirmations) with its txid matching, and the maker key, secret hash,
timeout, and amount must match the lot (the 1 EXCAL lot takes exactly
1 BTC, the pilot exactly 0.001 BTC). It then publishes the EXCAL claim
seed **encrypted to your delivery pubkey** in
`claim-seeds/<lot>-<funding_txid>.json`. Only you can decrypt it (see
`decrypt_seed.py`). The raw seed is never published — that is what stops
anyone front-running your claim after the secret appears.

**3. Lux claims your BTC — the secret appears on-chain.**
Lux spends your HTLC with the secret + his miner key. The secret is
then public in his claim transaction's witness (read it on
mempool.space). If Lux never claims, refund your BTC after your HTLC
timeout (your refund pubkey, `refund_tx_template` in `btc_htlc.py`).

**4. Claim the 1,000 EXCAL.**
```
python3 decrypt_seed.py --ciphertext claim-seeds/1k-<funding_txid>.json \
    --delivery-key delivery_key.txt
python3 taker_claim.py --secret <secret from step 3> \
    --claim-seed <from decrypt_seed.py> \
    --destination <your EXCAL LEGACY address, starting with 1...> [--lot 1excal]
```
**Your EXCAL destination must be a legacy address (1...).** The fork
accepts only its own opcode-free locks as outputs — a bc1q address is
not valid on the fork, and the script refuses it rather than building
an invalid claim. Use the legacy address for your key (same hash160 as
a Bitcoin legacy address).
`taker_claim.py` verifies the claim locally and refuses to print the hex
unless it validates. Post the signed hex as a comment on the lot's
GitHub issue (#2 for the 1,000 EXCAL lot, #3 for 1 EXCAL, #4 for the
pilot lot) — the fork node broadcasts it
and mines it into the next block. The EXCAL then lands at your
destination address (minus a 10,000-sword fee).

## Safety notes (read before funding)

- **Verify the EXCAL lock first.** Do not fund until you have confirmed
  the funding tx is in a fork block with the lot's EXCAL to the lock
  above. The lock, the secret hash, and the roots are all public.
- **One lot, one taker.** The secret is the same for everyone. The first
  funded HTLC is the one Lux claims. If a funding already exists, do
  not fund — your BTC would sit locked for 144 blocks and refund.
- **Claim promptly.** After the secret appears, claim the EXCAL right
  away. If you never claim, the EXCAL stays locked until fork height
  62898, when Lux can refund it — and your BTC is already gone.
- **Keep `delivery_key.txt` safe.** Lose it and you cannot decrypt the
  claim seed; without the seed you cannot claim the EXCAL.
- **The claim seed is never published raw.** Anyone telling you to send
  them the seed, or offering a different seed, is not part of this swap.

## Files

- `taker_htlc.py` — build your unsigned BTC HTLC funding PSBT (any amount).
- `decrypt_seed.py` — decrypt the published claim seed (needs `pip install cryptography`).
- `taker_claim.py` — build + sign the EXCAL claim (needs the excalibur-chain repo modules).
- `deliver_seed.py` — Lux-side watcher: verify funding, publish the encrypted seed.
- `claim_btc.py` — Lux-side: claim the BTC HTLC (dry run unless `--sign-and-broadcast`).
- `claim-seeds/` — published encrypted seeds, one file per funding, named `<lot>-<funding_txid>.json`.
