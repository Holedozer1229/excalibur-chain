"""Real-chain test for lightledger.py (test-only auditor key, throwaway).
Loads the live fork ChainState, exports the overlay snapshot at the tip,
attests a checkpoint, verifies it, then tampers (drops one coinbase UTXO)
and proves the fraud with an omission proof."""
import sys, os, json, time
sys.path.insert(0, '/home/hatch/workspace')
from chainstate import ChainState
import lightledger as ll

def dec_rec(r):
    r = dict(r)
    for k in ("prev", "merkle"):
        v = r[k]
        r[k] = bytes.fromhex(v) if isinstance(v, str) else bytes(v)
    r["txs"] = [bytes.fromhex(t) if isinstance(t, str) else t
                for t in r.get("txs", [])]
    return r

t0 = time.time()
cs = ChainState('/home/hatch/workspace/chaindata_fork', net='fork')
cs.load()
tip = cs.tips[0]
print(f"LOADED tip={tip['height']} hash={tip['hash'][:16]}... "
      f"work={tip['work']} in {time.time()-t0:.1f}s", flush=True)
u = cs.utxo
if hasattr(u, 'overlay'):  # UtxoSet over the Bitcoin snapshot
    overlay, spent = u.overlay, u.spent
else:  # plain dict: snapshot base not built on this VM, fork-only
    overlay, spent = u, set()
print(f"utxo-view: {'UtxoSet' if hasattr(u, 'overlay') else 'plain-dict'} spent_tombstones={len(spent)}", flush=True)
print(f"overlay={len(overlay)} spent_tombstones={len(spent)}", flush=True)

os.makedirs('/home/hatch/workspace/light-ledger', exist_ok=True)
out = '/home/hatch/workspace/light-ledger/overlay_snapshot_test.jsonl.gz'
man = ll.export_overlay(overlay, spent, tip['height'], tip['hash'],
                        tip['work'], out)
print("MANIFEST " + json.dumps(man), flush=True)
ov2, sp2 = ll.import_overlay(out, man)
print(f"IMPORT-OK overlay={len(ov2)} spent={len(sp2)}", flush=True)

key, root = ll.make_auditor_key('/tmp/ll_test_auditor.json',
                                '/tmp/ll_test_state.json')
fields = ll.make_checkpoint_fields(man)
cp = ll.attest_checkpoint(key, fields)
print(f"CHECKPOINT verify={ll.verify_checkpoint(cp)} leaf={cp['leaf_index']} "
      f"anchor={ll.anchor_hash(cp)[:32]}... status={ll.checkpoint_status(cp)} "
      f"status+25h={ll.checkpoint_status(cp, now=fields['issued_unix']+90000)}",
      flush=True)

# Tamper: drop one recent coinbase UTXO from the overlay.
items = ll.overlay_entries_sorted(overlay)
cbs = [(k, e) for k, e in items if e[0][2]]
drop_key, drop_entry = cbs[-1]
print(f"DROP target: txid={drop_key[0].hex()[:16]} vout={drop_key[1]} "
      f"cb_h={drop_entry[0][3]} value={drop_entry[0][0]}", flush=True)
tampered = dict(overlay)
del tampered[drop_key]
print("TAMPERED-ROOT-DIFFERS:",
      ll.overlay_root(tampered).hex() != man['overlay_root'], flush=True)
# The tampered set's manifest would not match the checkpoint — import
# of the honest file against a tampered manifest must fail:
bad_man = dict(man)
bad_man["overlay_root"] = ll.overlay_root(tampered).hex()
try:
    ll.import_overlay(out, bad_man)
    print("TAMPER-DETECTION FAILED (import accepted bad manifest)", flush=True)
except ValueError as e:
    print(f"TAMPER-DETECTED import rejected: {e}", flush=True)

# Fraud proof: the dropped coinbase UTXO was created by a confirmed block.
cb_h = drop_entry[0][3]
rec = None
with open('/home/hatch/workspace/chaindata_fork/chain.jsonl') as f:
    for line in f:
        r = json.loads(line)
        if r["height"] == cb_h:
            rec = dec_rec(r)
            break
assert rec is not None, "creating block not found"
from lightledger import header_hash
rbh = {header_hash(rec): rec}
# A checkpoint committing the TAMPERED root is the fraud under challenge.
cp_bad = dict(cp)
cp_bad["overlay_root"] = ll.overlay_root(tampered).hex()
cp_bad["overlay_count"] = len(tampered)
proof = ll.build_omission_proof(rbh, cp_bad, drop_key)
assert proof is not None, "omission proof build returned None"
proof = ll.attach_absence(cp_bad, proof, tampered)
ok, reason = ll.verify_omission_proof(cp_bad, proof, rbh)
print(f"FRAUD-PROOF vs tampered checkpoint: {ok} — {reason}", flush=True)
# And the honest checkpoint must NOT be fraud-provable (UTXO is present):
proof2 = ll.build_omission_proof(rbh, cp, drop_key)
proof2 = ll.attach_absence(cp, proof2, overlay)
ok2, reason2 = ll.verify_omission_proof(cp, proof2, rbh)
print(f"FRAUD-PROOF vs honest checkpoint: {ok2} — {reason2}", flush=True)
print("ALL-REAL-CHAIN-CHECKS-DONE", flush=True)
