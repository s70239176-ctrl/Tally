import datetime
import sys

import pytest

BASE = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
ORIGIN = "https://api.example.com"
URL_RE = r"^https://api\.example\.com/health$"


def iso(offset_s: int) -> str:
    return (BASE + datetime.timedelta(seconds=offset_s)).isoformat().replace("+00:00", "Z")


class Env:
    def __init__(self, vm, contract, alice, bob, carol):
        self.vm, self.c = vm, contract
        self.provider, self.consumer, self.other = alice, bob, carol
        self.t = 0

    def warp(self, offset_s):
        # genlayer-test 0.29.2: vm.warp() does not refresh the already-loaded
        # gl.message_raw['datetime'] that the contract reads, so sync it here.
        self.vm.warp(iso(offset_s))
        sys.modules["genlayer.gl"].message_raw["datetime"] = iso(offset_s)

    def as_(self, who):
        self.vm.sender = who

    def up(self):
        self._mock(200, "status: ok")

    def down(self, status=503, body="unavailable"):
        self._mock(status, body)

    def _mock(self, status, body):
        self.vm.clear_mocks()
        self.vm.mock_web(URL_RE, {"method": "GET", "status": status, "body": body})

    def unreachable(self):
        self.vm.clear_mocks()  # unmocked URL -> web call raises -> UNREACHABLE

    def register(self, **kw):
        args = dict(
            consumer=self.consumer.as_hex, origin=ORIGIN, probe_path="/health",
            expected_status=200, must_contain="ok", target_bps=9900,
            min_probes=4, min_interval_s=60,
        )
        args.update(kw)
        self.as_(self.provider)
        return self.c.register_sla(**args)

    def probe(self, sla_id, dt=60, who=None):
        self.t += dt
        self.warp(self.t)
        self.as_(who or self.other)
        return self.c.probe(sla_id)

    def claim(self, sla_id, dt=10):
        self.t += dt
        self.warp(self.t)
        self.as_(self.consumer)
        return self.c.open_claim(sla_id)


@pytest.fixture
def env(direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie):
    direct_vm.check_pickling = True
    direct_vm.warp(iso(0))
    contract = direct_deploy("contracts/uptime_sla.py")
    # A real network delivers calldata addresses as genlayer Address, not raw bytes.
    from genlayer.py.types import Address  # importable once the loader has staged the SDK
    a, b, c = (Address(x) if isinstance(x, bytes) else x for x in (direct_alice, direct_bob, direct_charlie))
    e = Env(direct_vm, contract, a, b, c)
    e.warp(0)
    return e
