# Decision record

## Selection

The primitive was **specified by the requester** ("an SLA / uptime claim for an API agent"), so the 10-candidate
scouting pass in the playbook was not run. What was done instead is the fit audit below.

## Collision audit (limited, and honest about the limit)

- Owner portfolio: only one other local project was inspected, Meridian (cross-chain escrow adjudication over
  submitted evidence). Different trust question (dispute over a deliverable) and different state model.
  `gh` was not installed, so the owner's remote repositories were **not** enumerated; a reviewer should treat
  the portfolio collision check as incomplete.
- Ecosystem: current GenLayer docs/examples were not re-fetched in this run. The playbook names "availability vs
  behavioral conformance" as a lane other primitives may occupy. This contract is deliberately the *availability*
  side, with the SLA and claim lifecycle attached, and does not judge behavioural correctness.

## Fit test

**Delete GenLayer: what breaks?** Someone must assert "the endpoint was down at time t". Without consensus that is
the provider (wants "up"), the consumer (wants "down"), or a monitoring operator (a new authority). GenLayer replaces
that with a probe that an independent validator set reproduced, and the claim can be computed only from such probes.

**Three consumers:** prepaid API billing credits, an agent-marketplace listing bond, a warranty/insurance pool.
(See `docs/INTEGRATION.md`.)

**Model-is-not-the-contract:** no model is used. Consensus witnesses a live observation with a substantive validator;
everything else is deterministic (admission, cooldown, ring buffer, uptime arithmetic, credit tiers).

**Hardest technical risk:** probe selection bias and validator egress. Documented in `docs/SECURITY.md`.

## Rejected design choices

- *LLM judging whether the response "looks healthy"*: adds nondeterminism for no information the status and marker
  don't already give; rejected.
- *Claim window chosen by the claimant*: enables cherry-picking; replaced with "all unclaimed probes, capped at the ring".
- *Anyone may claim*: lets a stranger consume a window early; replaced with a named consumer.
- *Money movement*: not included; the contract outputs a machine-readable `credit_bps` for a consumer to apply.
