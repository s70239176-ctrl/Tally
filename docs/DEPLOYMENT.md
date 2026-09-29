# Deployment evidence

## Canonical deployment (Studionet)

| | |
|---|---|
| Network | GenLayer Studionet |
| RPC / chain id | `https://studio.genlayer.com/api` / 61999 |
| Contract | `0x61F175c829F444A3715E14c6CffF4876F02CC20B` |
| Explorer | https://explorer-studio.genlayer.com/address/0x61F175c829F444A3715E14c6CffF4876F02CC20B |
| Deployed by | the repository owner, from Studio (deployer address and deploy tx hash **not yet recorded**; to be added by the owner) |
| Deployed source | 17,113 bytes, SHA-256 `0edb3854739a39ff0046c6c341e64ad7f7ba914458efa809656afd90f9ef2555` |
| Contract git blob | `87bfea28614d6b6483e221af7b22c4c45d1dd8fb` |
| Source parity | **MATCH**: the code read from the network via `gen_getContractCode` is byte-identical to `contracts/uptime_sla.py` at commit `55091e8` and at every later commit that leaves that file unchanged |
| Deployed schema | 12 methods (8 view, 4 write), no-argument constructor |

Checked on 2026-09-29. The deployment transaction's own lifecycle/finality has not been inspected here.

Tooling: Python 3.14.3, genlayer-test 0.29.2, genlayer-py 0.16.3, genvm-linter 0.11.0, GenVM SDK v0.2.16.

## Live evidence on the canonical contract

Produced by `tests/evidence/test_canonical_evidence.py`, run against the address above. Provider
`0x0485a76A62c714BaBf5315aBcfCf3BCDA910Ad5B`, consumer `0xcA46aC8f6Ca31d6218e0D7c48591C5489acFEE24` (a throwaway
account generated for the run). Endpoints: `https://httpbin.org/status/200` and `/status/503`. Every transaction
below reported status **ACCEPTED** and result **MAJORITY_AGREE**. None was observed as FINALIZED, and this document does
not claim finality.

| Scenario | Action | Tx | Stored result |
|---|---|---|---|
| success | register SLA 3 (`/status/200`) | `0x3b793e51638792b504934fc758d5d7e653b7b7d835cb9b86ba9608eff9f7a936` | SLA 3 created |
| success | probe SLA 3, rounds 1–3 | `0x79086cf3…c9ac9d9`, `0x473c7e71…15054`, `0x19ccfd7c…b9206` | 3 × UP |
| success | consumer opens claim | `0x0d13256e99c20d8ce7cf8c7a3e035ced80f8a132910b278947b97e91a955cfec` | claim 1: **MET**, uptime 10000 bps, credit 0 |
| negative | register SLA 4 (`/status/503`) | `0xcadc0ac4ed38fd63c7d6127d2e71f7eb52d2126c03e1f808fd0be7cd8f4eb7ce` | SLA 4 created |
| negative | probe SLA 4, rounds 1–3 | `0xba9409cc…d01e9`, `0xf7f84cee…d1d43`, `0x11a61f13…8a977` | 3 × DOWN |
| negative | consumer opens claim | `0x5e9ef21a9f4aecf6ed2cbc74988d8c2d347d5058605cc2fd2267f36803b4a3da` | claim 2: **BREACHED**, uptime 0 bps, credit 10000 |
| recovery | second claim on the same evidence | (disposable deployment, `tests/integration`) | rejected; window already consumed |

The canonical contract also holds SLAs 1–2 from a first evidence run that aborted mid-way on a DNS failure
(transport, before the test finished). Their consumer key was discarded, so nobody can claim them. They are inert.

## Integration suite

`gltest tests/integration/ -v -s --network studionet`: 3 passed in 8m34s. These tests deploy **disposable**
contracts; they are not the canonical deployment.

## Local gates

Direct Mode 81 passed; `genvm-lint lint` passed; `genvm-lint check` passed (exit 0).
