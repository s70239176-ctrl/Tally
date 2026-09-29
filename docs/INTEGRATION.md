# Integrating Tally (`UptimeSLA`)

A consumer contract needs no web access, no prompts and no knowledge of probing. It reads a claim.

```python
@gl.contract_interface
class IUptimeSLA:
    class View:
        def is_breached(self, claim_id: int) -> bool: ...
        def credit_bps(self, claim_id: int) -> int: ...
        def claim_matches_definition(self, claim_id: int, expected_definition_hash: str) -> bool: ...


class ServiceCredits(gl.Contract):
    def apply_credit(self, sla_address: str, claim_id: int, expected_hash: str) -> int:
        sla = IUptimeSLA(Address(sla_address))
        if not sla.view().claim_matches_definition(claim_id, expected_hash):
            raise gl.vm.UserError("EXPECTED: claim was not made against the agreed SLA terms")
        if not sla.view().is_breached(claim_id):
            raise gl.vm.UserError("EXPECTED: no breach")
        return sla.view().credit_bps(claim_id)  # e.g. 2500 = 25% of the period fee
```

(Interface shown for illustration; it is not shipped as a second executable contract. Verify the
`contract_interface` syntax against your installed SDK.)

## Three unrelated consumers

1. **Prepaid API billing**: prorates the next invoice by `credit_bps`.
2. **Agent marketplace**: delists or slashes a listing bond when a claim is `BREACHED`.
3. **Insurance / warranty pool**: pays out a fixed schedule from `credit_bps` tiers.

## Reading it

| View | Use |
|---|---|
| `definition_hash(sla_id)` | Pin the terms you agreed to. |
| `get_claim(claim_id)` | Full receipt: probe range, up/total, uptime bps, verdict, credit, definition hash. |
| `is_breached(claim_id)`, `credit_bps(claim_id)` | Gates. |
| `window_uptime(sla_id)` | Informational uptime over the newest ≤32 probes. |
| `get_probe(sla_id, seq)` | Audit any probe still in the ring window. |

Pull, don't trust: the contract emits no callbacks, so a consumer re-reads the stored claim.
