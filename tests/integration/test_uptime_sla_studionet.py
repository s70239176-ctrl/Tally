"""Real-consensus Studionet tests. Each test deploys its own disposable contract.

Run:  gltest tests/integration/ -v -s --network studionet

Probes must be >= min_interval_s (60s) apart in *chain* time, so these tests really wait.
Endpoints are httpbin.org's deterministic status endpoints (public, no auth).
"""
import time

from gltest import create_account, get_contract_factory, get_default_account
from gltest.assertions import tx_execution_succeeded

ORIGIN = "https://httpbin.org"
GAP_S = 65


def _deploy():
    factory = get_contract_factory(contract_file_path="uptime_sla.py")
    return factory.deploy(account=get_default_account(), consensus_max_rotations=3)


def _register(c, consumer, path, expected, target=9900, min_probes=3):
    r = c.register_sla(
        args=[consumer.address, ORIGIN, path, expected, "", target, min_probes, 60]
    ).transact(consensus_max_rotations=3)
    assert tx_execution_succeeded(r)
    assert c.get_sla(args=[1]).call()["origin"] == ORIGIN  # setup really created state
    return 1


def _probe_n(c, sla_id, n):
    for i in range(n):
        if i:
            time.sleep(GAP_S)
        r = c.probe(args=[sla_id]).transact(consensus_max_rotations=3)
        assert tx_execution_succeeded(r)


def test_deploy_and_public_surface():
    c = _deploy()
    consumer = create_account()
    sid = _register(c, consumer, "/status/200", 200)
    s = c.get_sla(args=[sid]).call()
    assert s["active"] is True and s["probe_count"] == 0
    assert len(c.definition_hash(args=[sid]).call()) == 64


def test_live_uptime_met_path():
    c = _deploy()
    consumer = create_account()
    sid = _register(c, consumer, "/status/200", 200)
    _probe_n(c, sid, 3)
    assert c.window_uptime(args=[sid]).call()["uptime_bps"] == 10000
    r = c.connect(consumer).open_claim(args=[sid]).transact(consensus_max_rotations=3)
    assert tx_execution_succeeded(r)
    claim = c.get_claim(args=[1]).call()
    assert claim["verdict"] == "MET" and claim["credit_bps"] == 0
    assert c.is_breached(args=[1]).call() is False


def test_live_breach_path_and_evidence_consumed():
    c = _deploy()
    consumer = create_account()
    sid = _register(c, consumer, "/status/503", 200)  # endpoint really returns 503
    _probe_n(c, sid, 3)
    assert c.get_probe(args=[sid, 1]).call()["outcome"] == "DOWN"
    r = c.connect(consumer).open_claim(args=[sid]).transact(consensus_max_rotations=3)
    assert tx_execution_succeeded(r)
    claim = c.get_claim(args=[1]).call()
    assert claim["verdict"] == "BREACHED" and claim["uptime_bps"] == 0
    assert c.credit_bps(args=[1]).call() == 10000
    assert c.is_breached(args=[1]).call() is True
    # the same evidence cannot back a second claim
    r2 = c.connect(consumer).open_claim(args=[sid]).transact(consensus_max_rotations=3)
    assert not tx_execution_succeeded(r2)
    assert c.get_sla(args=[sid]).call()["last_claimed_seq"] == 3
