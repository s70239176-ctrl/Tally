# Submission

**Title:** Tally: consensus-witnessed uptime claims for API agents

**One-line thesis:** Tally is a reusable GenLayer primitive that turns validator-witnessed endpoint probes into a
deterministic SLA claim (BREACHED / MET plus a credit tier) that other contracts can read.

**Category:** standalone Intelligent Contract

**Repository:** https://github.com/s70239176-ctrl/Tally

**Canonical Studionet address:** `0x61F175c829F444A3715E14c6CffF4876F02CC20B`

**Explorer URL (genlayer-explorer-contract):**
https://explorer-studio.genlayer.com/address/0x61F175c829F444A3715E14c6CffF4876F02CC20B

**Deployment tx:** `0x353f11290bb3047801076d3c31a9cf16d81938a17dd35098902ed882ec041874` (deployer `0x5F512824Eb3785Fa3F3532158c288A27B9b5Fc58`; status FINALIZED, MAJORITY_AGREE)

**Deployment source:** `contracts/uptime_sla.py`, git blob `87bfea28614d6b6483e221af7b22c4c45d1dd8fb`, byte-identical to the
code read from the deployed address (`docs/DEPLOYMENT.md`).

**Why GenLayer is required:** "the endpoint was down at time t" would otherwise be asserted by the provider, the
consumer or a trusted monitor. Here it is an observation independent validators reproduced.

**Consensus mechanism:** `run_nondet_unsafe` around one web fetch. The validator type-checks the leader's proposal and
independently re-fetches; outcome classes must match. No LLM. See `docs/CONSENSUS.md`.

**Deterministic responsibilities:** URL admission, cooldown, 32-slot ring buffer, uptime arithmetic, credit tiers,
claim gating, evidence consumption, staleness check.

**Failure policy:** unreachable or wrong response counts as not-up; too few probes reverts the claim; validator
disagreement changes no state.

**Reuse surface:** `is_breached`, `credit_bps`, `claim_matches_definition` (`docs/INTEGRATION.md`).

**Test results (verified):** 81 Direct Mode tests passed; GenVM lint and SDK validation passed; 3 Studionet
integration tests passed; live MET and BREACHED claims recorded on the canonical contract (deploy tx FINALIZED / MAJORITY_AGREE; probe and claim txs recorded as ACCEPTED / MAJORITY_AGREE).

**Limitations:** probe selection bias, validator egress dependence, availability rather than answer quality, defence-in-depth
URL checks, not audited, Studionet only. Owner-portfolio collision check incomplete (`DECISION.md`).

**Reviewer fast path:** see README "Reproduce".

## Portal description (under 1000 characters)

Tally is a standalone GenLayer Intelligent Contract for API-agent SLA claims. A provider registers an immutable uptime SLA for an HTTPS endpoint and names one consumer. Anyone can trigger a probe: the leader fetches the endpoint, each validator independently re-fetches, and the probe is stored only if they agree on UP, DOWN or UNREACHABLE. The consumer's claim is deterministic arithmetic over unclaimed consensus-witnessed probes, giving BREACHED or MET and a credit tier, and it consumes its evidence so it cannot be double-counted. The contract moves no funds; other contracts read is_breached / credit_bps. Verified with 81 Direct Mode tests, GenVM lint and SDK validation, 3 live Studionet integration tests, and live MET and BREACHED claims on the deployed contract (transactions ACCEPTED, MAJORITY_AGREE).
