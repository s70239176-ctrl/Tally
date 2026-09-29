"""Records live evidence against the CANONICAL deployment (not a disposable one).

    CANONICAL_ADDRESS=0x... gltest tests/evidence/ -v -s --network studionet

Registers two SLAs on the canonical contract (one healthy endpoint, one that returns 503),
probes both three times (>=60s apart in chain time), opens a claim on each, and prints every
transaction hash plus the stored results as JSON between EVIDENCE markers. Each run appends
new SLAs/claims to the canonical contract's state; that is intended, it is the evidence.
"""
import json
import os
import time

from gltest import create_account, get_contract_factory, get_default_account
from gltest.assertions import tx_execution_succeeded

ORIGIN = "https://httpbin.org"
GAP_S = 65


def _tx(r):
    return {"hash": r["hash"], "status": r.get("status_name", r.get("status")),
            "result": r.get("result_name", r.get("result"))}


def test_canonical_met_and_breached():
    address = os.environ["CANONICAL_ADDRESS"]
    factory = get_contract_factory(contract_file_path="uptime_sla.py")
    provider = get_default_account()
    consumer = create_account()  # generated in-process; key is never printed
    c = factory.build_contract(address, account=provider)
    ev = {"contract": address, "provider": provider.address, "consumer": consumer.address, "txs": {}}

    ids = {}
    for label, path in (("met", "/status/200"), ("breach", "/status/503")):
        r = c.register_sla(
            args=[consumer.address, ORIGIN, path, 200, "", 9900, 3, 60]
        ).transact(consensus_max_rotations=3)
        assert tx_execution_succeeded(r)
        ev["txs"][f"register_{label}"] = _tx(r)

    # SLA ids are monotonic; find ours as the two newest SLAs owned by this provider/consumer pair.
    # Probe ids upward from a generous bound until the two newest registered are located.
    found = []
    sid = 1
    while True:
        try:
            s = c.get_sla(args=[sid]).call()
        except Exception:
            break
        if s["consumer"].lower() == consumer.address.lower():
            found.append((sid, s["probe_path"]))
        sid += 1
    ids = {"met": [i for i, p in found if p == "/status/200"][0],
           "breach": [i for i, p in found if p == "/status/503"][0]}
    ev["sla_ids"] = ids

    for rnd in range(3):
        if rnd:
            time.sleep(GAP_S)
        for label in ("met", "breach"):
            r = c.probe(args=[ids[label]]).transact(consensus_max_rotations=3)
            assert tx_execution_succeeded(r)
            ev["txs"][f"probe_{label}_{rnd + 1}"] = _tx(r)

    cc = c.connect(consumer)
    for label in ("met", "breach"):
        r = cc.open_claim(args=[ids[label]]).transact(consensus_max_rotations=3)
        assert tx_execution_succeeded(r)
        ev["txs"][f"claim_{label}"] = _tx(r)

    claims = {}
    cid = 1
    while True:
        try:
            cl = c.get_claim(args=[cid]).call()
        except Exception:
            break
        if cl["claimant"].lower() == consumer.address.lower():
            claims[cl["sla_id"]] = (cid, cl)
        cid += 1
    met_id, met = claims[ids["met"]]
    br_id, br = claims[ids["breach"]]
    ev["claims"] = {"met": {"claim_id": met_id, **met}, "breach": {"claim_id": br_id, **br}}

    assert met["verdict"] == "MET" and met["credit_bps"] == 0 and met["uptime_bps"] == 10000
    assert br["verdict"] == "BREACHED" and br["uptime_bps"] == 0 and br["credit_bps"] == 10000
    assert c.is_breached(args=[met_id]).call() is False
    assert c.is_breached(args=[br_id]).call() is True

    print("EVIDENCE_BEGIN")
    print(json.dumps(ev, indent=2, default=str))
    print("EVIDENCE_END")
