# Security model

## Assets

The claim verdict (`BREACHED` / `MET`) and credit tier, which a downstream contract may use to move value;
and the integrity of the probe record it is computed from.

## Actors

Provider (registers, may deactivate), consumer (only party who can claim), any prober (anyone may `probe`),
the endpoint owner (usually the provider), the endpoint content (untrusted), a malicious leader, honest validators,
a minority of malicious validators, and downstream consumer contracts.

## Trust assumptions

- A majority of validators is honest and their egress can reach the public internet.
- The endpoint's behaviour, as seen by validators at probe time, is what the SLA is about.
- Studionet is a development network; this is not a production audit.

## Input attacks and defences

| Attack | Defence |
|---|---|
| SSRF-style origins (http, credentials, ports, localhost, `.local`, `.internal`, IP literals, uppercase/odd labels) | Deterministic admission in `_validate_origin`; TLD must be alphabetic (rejects IPv4-shaped hosts); no ports; no colon hosts (so no IPv6). |
| Path tricks (`//host`, `..`, schemes, `#`, `@`, whitespace) | `_validate_path` requires a single leading `/` and printable ASCII, and rejects `..`, `://`, `\`, `#`, `@`. The origin is stored separately, so a probe path can't change host. |
| Prompt injection via body | No model reads the body. The body is only searched for a fixed marker in the first 4096 bytes. |
| Oversized inputs | Origin ≤120, path ≤160, marker ≤64, body examined ≤4096 bytes, ring = 32 slots per SLA. |
| Forged leader | Validator recomputes the observation independently and type-checks strictly (bool/float/hex/unknown enum/extra key/missing key). |
| Caller-supplied evidence | `probe` and `open_claim` take only an id. Outcomes come solely from consensus. |
| Double credit | A claim consumes its probe window (`last_claimed_seq`); the same probes cannot back another claim. |
| Stale evidence | A claim reverts if the newest probe is older than 7 days. |
| Replay / reentrancy | State is written before returning; the contract sends no messages and holds no funds. |
| Terms changed after the fact | The SLA definition is immutable and hashed; each claim stores the hash, and `claim_matches_definition` lets a consumer check it. |

## Fail-open / fail-closed

- Unreachable, wrong status, missing marker → not-up (a probe that can't show health does not count as up).
- Fewer than `min_probes` unclaimed probes → the claim reverts; no verdict is manufactured.
- Unknown claim ids → `is_breached` is `false`; `credit_bps` reverts.

## Known limitations (be honest)

- **Selection bias.** Anyone can trigger probes, so a claimant can time probes into an outage. Mitigations:
  the per-SLA cooldown (≥60 s), all probes since the last claim count (no cherry-picking inside a window), and the
  provider can probe too. Time-of-day coverage is not enforced.
- **Egress dependence.** If validators can't reach an endpoint that is up for everyone else (regional blocks,
  allow-lists), it will be recorded as down. The provider must allow validator traffic.
- **Probe-path health ≠ agent correctness.** This attests availability plus an optional body marker, not answer quality.
- The URL checks are defence in depth, not a complete SSRF guarantee; validator egress policy also matters.
- Unbounded number of SLAs (each is a fixed-size record plus ≤32 probe slots).
- Not audited.
