# Tally: consensus-witnessed uptime claims for API agents

Tally (contract class `UptimeSLA`) is a standalone GenLayer Intelligent Contract. A provider registers an immutable SLA for an HTTPS
endpoint. Validators independently probe the endpoint and agree on UP / DOWN / UNREACHABLE. The named consumer can then
open a claim, and deterministic arithmetic over the consensus-witnessed probes returns BREACHED or MET with a credit tier.
The contract moves no funds; other contracts read `is_breached` / `credit_bps`.

## Status (what has actually been verified)

| Gate | Result |
|---|---|
| Direct Mode (`tests/direct`) | 81 passed, 0 failed (needs the Windows shim on Windows, see below) |
| GenVM AST lint (`genvm-lint` 0.11.0) | passed (3 checks) |
| GenVM SDK validate (`genvm-lint check`) | passed, exit 0 (12 methods: 8 view, 4 write). Note: it reports a newer py-genlayer runner exists than the one pinned in the header |
| Studionet integration (`tests/integration`) | 3 passed, real consensus, disposable deployments |
| Canonical Studionet deployment | `0x61F175c829F444A3715E14c6CffF4876F02CC20B`, source byte-identical to `main`; live MET and BREACHED claims recorded, see `docs/DEPLOYMENT.md` (txs ACCEPTED, not observed FINALIZED) |

Environment: Python 3.14.3, genlayer-test 0.29.2, genlayer-py 0.16.3, GenVM SDK v0.2.16.

## Why GenLayer

Someone has to assert "the endpoint was down at time t". Without consensus that is the provider, the consumer, or a
monitoring operator, each a party with a stake or a new authority. Here every recorded probe is an observation that
independent validators reproduced, and a claim can be computed only from those. Details: `docs/CONSENSUS.md`,
`DECISION.md`.

## Flow

1. `register_sla(consumer, origin, probe_path, expected_status, must_contain, target_bps, min_probes, min_interval_s)`:
   provider registers; terms are hashed and immutable. `deactivate` is the only later change.
2. `probe(sla_id)`: anyone, at most once per `min_interval_s`. The leader fetches, validators each fetch
   independently, and the result is stored only if they agree on the outcome class.
3. `open_claim(sla_id)`: consumer only. Uses unclaimed probes (up to 32), needs at least `min_probes`, and the newest
   probe must be under 7 days old. Verdict is BREACHED when `up*10000//n < target_bps`. Credit tiers by shortfall
   (bps): <100 → 1000, <500 → 2500, <2000 → 5000, otherwise 10000. The window is then consumed.

Views: `get_sla`, `definition_hash`, `get_probe`, `window_uptime`, `get_claim`, `is_breached`, `credit_bps`,
`claim_matches_definition`. Consumer example: `docs/INTEGRATION.md`.

## Deterministic vs nondeterministic

Nondeterministic: one live web fetch per probe (validated by independent re-fetch). Everything else is deterministic:
URL admission, cooldown, ring buffer, uptime arithmetic, credit tiers, claim gating. No LLM.

## Limitations

Probe selection bias, validator egress dependence, availability rather than answer quality, defence-in-depth URL checks,
not audited, Studionet only. See `docs/SECURITY.md`.

## Reproduce

```bash
python -m venv .venv-test && .venv-test/Scripts/python -m pip install -r requirements-test.txt
# Direct Mode (Windows needs the shim; other OSes can drop the -p flag)
PYTHONPATH=. .venv-test/Scripts/python -m pytest tests/direct -q -p tests.support.win_direct_shim
# Lint (separate venv with genvm-linter; PYTHONUTF8=1 avoids a Windows console encoding crash)
PYTHONUTF8=1 genvm-lint lint contracts/uptime_sla.py
# Live, takes ~9 minutes because probes must be >=60s apart in chain time
gltest tests/integration/ -v -s --network studionet
```

### Windows host workaround

On Windows, genlayer-test 0.29.2's Direct Mode loader fails with `WinError 32` before any contract code runs (it
unlinks a temp file still held open as fd 0). `tests/support/win_direct_shim.py` replaces only that one loader function
with a copy that defers the unlink. It does not touch the contract or patch `os.unlink` globally, and it is a no-op
off Windows. Also note that `vm.warp()` in this version does not refresh `gl.message_raw["datetime"]`, so the test
helper syncs it.
