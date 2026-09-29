# Consensus design

## 1. The one nondeterministic call

`UptimeSLA.probe(sla_id)` is the only place validators must agree on something they observe live.

| | |
|---|---|
| Call | `gl.vm.run_nondet_unsafe(leader, validator)` wrapping `gl.nondet.web.request(url, method="GET")` |
| Input | `url = origin + probe_path` (immutable, admission-checked at registration), `expected_status`, optional `must_contain` marker |
| Output | `{"outcome": "UP" \| "DOWN" \| "UNREACHABLE", "status": int}` |
| Why deterministic code can't do it | The contract cannot open a socket. Whether an endpoint is up *now* is a fact only observers can supply. |

No LLM is used. The judgment is a live observation, not a semantic interpretation, and everything after it
is arithmetic. Using a model here would add nondeterminism without adding information.

## 2. Leader

1. Fetch `url` with GET.
2. Network error → `UNREACHABLE`, status 0.
3. Status ≠ `expected_status` → `DOWN`, that status.
4. If `must_contain` is set and it is absent from the first 4096 bytes of the body → `DOWN`.
5. Otherwise `UP`.

## 3. Validator

Each validator:

1. Rejects any leader result that is not a `gl.vm.Return` (leader error → reject).
2. Type-checks the proposal strictly (`type(x) is dict`, exact key set, `type(status) is int`, so `True` and `200.0`
   are rejected; outcome in the closed enum; status in 0..599; `UP` must carry exactly `expected_status`;
   `DOWN` must carry a real non-zero status; `UNREACHABLE` must carry 0).
3. **Independently performs its own fetch and classification** with the same function.
4. Accepts iff its own `outcome` equals the leader's.

A perfectly well-formed but false leader result is rejected because step 3 recomputes the truth
(`tests/direct/test_uptime_sla_hardening.py`: forged UP vs validator-sees-DOWN, forged UP vs unreachable,
forged DOWN vs validator-sees-UP, DOWN/UNREACHABLE swap).

## 4. Equivalence

Must match: the outcome class.

May differ: the HTTP status *within* a failure (a leader seeing 500 and a validator seeing 502 are both `DOWN`).
The stored status is the leader's and is informational; no decision reads it.

Not equivalent: `UP` vs `DOWN`; `DOWN` vs `UNREACHABLE`; reachable vs unreachable.

`strict_eq` is not used, because response bodies, headers and timing legitimately differ between validators.

## 5. Failure handling

| Situation | Behaviour |
|---|---|
| Endpoint unreachable | Recorded as `UNREACHABLE` only if validators agree. It counts as not-up. |
| Endpoint flaps between validators | No agreement → the transaction is not accepted at protocol level (`UNDETERMINED`). No state changes; the probe can be retried after the cooldown. |
| Leader crashes / malformed result | Validators reject; no state change. |
| Protocol `UNDETERMINED` | Distinct from any contract result. The contract stores nothing for it. |

## 6. Why consensus is load-bearing

Remove consensus and one party has to say "the endpoint was down at time *t*": the provider (who wants to say up),
the consumer (who wants to say down), or a trusted monitor (a new authority). With consensus, each recorded
probe is an observation that an independent validator set reproduced, and the claim is computed only from those.
The deterministic claim step cannot fabricate downtime that no validator quorum witnessed.

## 7. Multiple stages

Observation (`probe`, consensus) and judgment (`open_claim`, deterministic arithmetic) are separate transactions,
so each has one clear rule and the claim path costs no consensus round.
