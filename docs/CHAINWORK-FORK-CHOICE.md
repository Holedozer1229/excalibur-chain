# EXCAL chainwork fork-choice policy

EXCAL's fork choice compares cumulative proof-of-work. A node-local wall-clock
exception must not determine whether a valid higher-work branch is accepted:
two nodes with identical block data but different uptime would otherwise
disagree about the same candidate branch.

The previous implementation rejected reorganizations deeper than 100 blocks
unless the local node's current tip timestamp was more than 200 expected block
intervals behind the machine's current wall clock. That exception was not
deterministic consensus: a sleeping node and an online node could make
different decisions about the same block.

The change in this branch removes that local-clock gate and returns to
chainwork-only fork selection. It does not alter block validity, proof-of-work
calculation, transaction signatures, wallet rules, or UTXO serialization.

## Rollout warning

This changes deep-reorganization behavior for upgraded nodes. It must be
reviewed and coordinated before release; do not mix old and new node versions
during a chain split or planned deep reorganization. A deep reorganization
should trigger operator alerting, independent peer comparison, and forensic
review, but it must not be accepted/rejected based on local uptime.

## Tests

`tests/test_chainwork_fork_choice.py` verifies that higher cumulative work
wins, while equal or lower work does not trigger a reorganization. Full
multi-node branch, restart, and deep-reorg tests remain required before
production activation.
