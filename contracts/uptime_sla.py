# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

"""UptimeSLA: consensus-witnessed uptime for an API agent, and a deterministic SLA claim on top of it.

The provider of an API agent registers an SLA: an HTTPS origin + probe path, the
status (and optional body marker) that counts as healthy, a target uptime in basis
points, and a named consumer. The definition is immutable.

Anyone may `probe` an active SLA. Each probe is a GenLayer consensus observation:
the leader fetches the endpoint, every validator fetches it independently, and the
probe only lands in state if the validators agree on the outcome class
(UP / DOWN / UNREACHABLE). Probes live in a fixed-size ring buffer.

The consumer may `open_claim`. A claim is pure deterministic arithmetic over the
consensus-witnessed probes that have not been claimed before: uptime = up / total,
BREACHED when below target, with a credit tier derived from the shortfall. Nothing
in the claim path calls a model or the web; the model-free consensus is in `probe`.

The contract never moves funds. Consumers read `is_breached` / `credit_bps`.
"""

import datetime
import hashlib
import json
from dataclasses import dataclass

from genlayer import *

UP = "UP"
DOWN = "DOWN"
UNREACHABLE = "UNREACHABLE"
_OUTCOMES = (UP, DOWN, UNREACHABLE)

BREACHED = "BREACHED"
MET = "MET"

WINDOW = 32  # ring-buffer slots per SLA; also the max probes a claim can cover
MAX_ORIGIN = 120
MAX_PATH = 160
MAX_MATCH = 64
MAX_BODY_CHARS = 4096  # bytes of response body examined for the marker
MIN_PROBES_FLOOR = 3
MIN_INTERVAL_FLOOR_S = 60
MAX_EVIDENCE_AGE_S = 7 * 24 * 3600
_ZERO = "0x" + "00" * 20


@allow_storage
@dataclass
class SLA:
    provider: Address
    consumer: Address
    origin: str
    probe_path: str
    must_contain: str
    expected_status: u256
    target_bps: u256
    min_probes: u256
    min_interval_s: u256
    definition_hash: str
    active: bool
    probe_count: u256
    last_probe_ts: u256
    last_claimed_seq: u256


@allow_storage
@dataclass
class Probe:
    seq: u256
    ts: u256
    outcome: str
    http_status: u256


@allow_storage
@dataclass
class Claim:
    sla_id: u256
    claimant: Address
    definition_hash: str
    first_seq: u256
    last_seq: u256
    probes: u256
    up: u256
    uptime_bps: u256
    target_bps: u256
    verdict: str
    credit_bps: u256
    opened_ts: u256
    evidence_age_s: u256


def _err(msg: str) -> "gl.vm.UserError":
    return gl.vm.UserError(msg)


def _validate_origin(origin: str) -> str:
    """Defence in depth only; validator egress policy still matters."""
    if not isinstance(origin, str) or len(origin) > MAX_ORIGIN:
        raise _err("EXPECTED: origin too long or not a string")
    if not origin.startswith("https://"):
        raise _err("EXPECTED: origin must be https://")
    host = origin[len("https://"):]
    if host.endswith("/"):
        host = host[:-1]
    if host == "" or "/" in host or "@" in host or ":" in host or "?" in host or "#" in host:
        raise _err("EXPECTED: origin must be a bare host (no path, port, credentials)")
    if host != host.lower():
        raise _err("EXPECTED: origin host must be lowercase")
    labels = host.split(".")
    if len(labels) < 2:
        raise _err("EXPECTED: origin host needs a public domain")
    for label in labels:
        if label == "" or len(label) > 63 or label[0] == "-" or label[-1] == "-":
            raise _err("EXPECTED: malformed DNS label")
        for ch in label:
            if not (ch.isascii() and (ch.isalnum() or ch == "-")):
                raise _err("EXPECTED: malformed DNS label")
    if not labels[-1].isalpha():
        raise _err("EXPECTED: numeric/IP-style hosts are rejected")
    if host == "localhost" or labels[-1] in ("localhost", "local", "internal", "localdomain", "lan", "home"):
        raise _err("EXPECTED: non-public host suffix rejected")
    return "https://" + host


def _validate_path(path: str) -> str:
    if not isinstance(path, str) or len(path) > MAX_PATH:
        raise _err("EXPECTED: probe path too long or not a string")
    if not path.startswith("/") or path.startswith("//"):
        raise _err("EXPECTED: probe path must be a relative path starting with a single /")
    for ch in path:
        if ord(ch) < 0x21 or ord(ch) > 0x7E or ch in "\\#@":
            raise _err("EXPECTED: probe path has forbidden characters")
    if ".." in path or "://" in path:
        raise _err("EXPECTED: probe path must not escape or embed a scheme")
    return path


def _parse_ts(iso: str) -> int:
    dt = datetime.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return int(dt.timestamp())


def _definition_hash(provider: str, consumer: str, origin: str, path: str, must: str,
                     status: int, target: int, min_probes: int, interval: int) -> str:
    blob = json.dumps(
        [provider, consumer, origin, path, must, status, target, min_probes, interval],
        separators=(",", ":"),
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _observe(url: str, expected_status: int, must_contain: str) -> dict:
    """One live observation. Returns only bounded, typed fields; never raises on network errors."""
    try:
        resp = gl.nondet.web.request(url, method="GET")
        status = int(resp.status)
        raw = resp.body or b""
    except Exception:
        return {"outcome": UNREACHABLE, "status": 0}
    if status != expected_status:
        return {"outcome": DOWN, "status": status}
    if must_contain != "":
        text = raw[:MAX_BODY_CHARS].decode("utf-8", errors="ignore")
        if must_contain not in text:
            return {"outcome": DOWN, "status": status}
    return {"outcome": UP, "status": status}


def _obs_well_formed(obs: object, expected_status: int) -> bool:
    """Strict type/shape check of a leader proposal. bool is not an int here."""
    if type(obs) is not dict or set(obs.keys()) != {"outcome", "status"}:
        return False
    outcome = obs["outcome"]
    status = obs["status"]
    if type(outcome) is not str or outcome not in _OUTCOMES:
        return False
    if type(status) is not int or status < 0 or status > 599:
        return False
    if outcome == UP and status != expected_status:
        return False
    if outcome == DOWN and status == 0:
        return False
    if outcome == UNREACHABLE and status != 0:
        return False
    return True


def _slot(sla_id: int, seq: int) -> str:
    return f"{sla_id}:{seq % WINDOW}"


def _credit_bps(target_bps: int, uptime_bps: int) -> int:
    """Deterministic credit tiers from the uptime shortfall (basis points)."""
    shortfall = target_bps - uptime_bps
    if shortfall <= 0:
        return 0
    if shortfall < 100:
        return 1000
    if shortfall < 500:
        return 2500
    if shortfall < 2000:
        return 5000
    return 10000


class UptimeSLA(gl.Contract):
    sla_count: u256
    claim_count: u256
    slas: TreeMap[u256, SLA]
    probes: TreeMap[str, Probe]
    claims: TreeMap[u256, Claim]

    def __init__(self):
        self.sla_count = u256(0)
        self.claim_count = u256(0)

    # ---------------------------------------------------------------- helpers

    def _sla(self, sla_id: int) -> SLA:
        key = u256(sla_id)
        if key not in self.slas:
            raise _err("EXPECTED: unknown sla_id")
        return self.slas[key]

    # ------------------------------------------------------------------ writes

    @gl.public.write
    def register_sla(
        self,
        consumer: str,
        origin: str,
        probe_path: str,
        expected_status: int,
        must_contain: str,
        target_bps: int,
        min_probes: int,
        min_interval_s: int,
    ) -> int:
        origin = _validate_origin(origin)
        probe_path = _validate_path(probe_path)
        if not isinstance(must_contain, str) or len(must_contain) > MAX_MATCH:
            raise _err("EXPECTED: must_contain too long")
        if expected_status < 100 or expected_status > 599:
            raise _err("EXPECTED: expected_status out of range")
        if target_bps < 1 or target_bps > 9999:
            raise _err("EXPECTED: target_bps must be 1..9999")
        if min_probes < MIN_PROBES_FLOOR or min_probes > WINDOW:
            raise _err("EXPECTED: min_probes must be 3..32")
        if min_interval_s < MIN_INTERVAL_FLOOR_S:
            raise _err("EXPECTED: min_interval_s must be >= 60")
        provider = gl.message.sender_address
        if not isinstance(consumer, str) or len(consumer) != 42 or not consumer.startswith("0x"):
            raise _err("EXPECTED: consumer must be a 0x-prefixed 20-byte hex address")
        try:
            consumer_addr = Address(consumer)
        except Exception:
            raise _err("EXPECTED: consumer is not a valid address")
        if consumer_addr.as_hex == _ZERO or consumer_addr == provider:
            raise _err("EXPECTED: consumer must be a distinct non-zero address")

        sla_id = int(self.sla_count) + 1
        self.sla_count = u256(sla_id)
        self.slas[u256(sla_id)] = SLA(
            provider=provider,
            consumer=consumer_addr,
            origin=origin,
            probe_path=probe_path,
            must_contain=must_contain,
            expected_status=u256(expected_status),
            target_bps=u256(target_bps),
            min_probes=u256(min_probes),
            min_interval_s=u256(min_interval_s),
            definition_hash=_definition_hash(
                provider.as_hex, consumer_addr.as_hex, origin, probe_path, must_contain,
                expected_status, target_bps, min_probes, min_interval_s,
            ),
            active=True,
            probe_count=u256(0),
            last_probe_ts=u256(0),
            last_claimed_seq=u256(0),
        )
        return sla_id

    @gl.public.write
    def deactivate(self, sla_id: int) -> None:
        sla = self._sla(sla_id)
        if gl.message.sender_address != sla.provider:
            raise _err("EXPECTED: only the provider may deactivate")
        sla.active = False

    @gl.public.write
    def probe(self, sla_id: int) -> dict:
        sla = self._sla(sla_id)
        if not sla.active:
            raise _err("EXPECTED: sla is not active")
        now = _parse_ts(gl.message_raw["datetime"])
        count = int(sla.probe_count)
        if count > 0 and now < int(sla.last_probe_ts) + int(sla.min_interval_s):
            raise _err("EXPECTED: probe cooldown has not elapsed")

        url = str(sla.origin) + str(sla.probe_path)
        expected = int(sla.expected_status)
        must = str(sla.must_contain)

        def leader() -> dict:
            return _observe(url, expected, must)

        def validator(res: gl.vm.Result) -> bool:
            if not isinstance(res, gl.vm.Return):
                return False
            proposed = res.calldata
            if not _obs_well_formed(proposed, expected):
                return False
            mine = _observe(url, expected, must)
            return mine["outcome"] == proposed["outcome"]

        obs = gl.vm.run_nondet_unsafe(leader, validator)
        if not _obs_well_formed(obs, expected):
            raise _err("EXTERNAL: malformed consensus observation")

        seq = count + 1
        self.probes[_slot(sla_id, seq)] = Probe(
            seq=u256(seq),
            ts=u256(now),
            outcome=obs["outcome"],
            http_status=u256(obs["status"]),
        )
        sla.probe_count = u256(seq)
        sla.last_probe_ts = u256(now)
        return {"sla_id": sla_id, "seq": seq, "outcome": obs["outcome"], "status": obs["status"]}

    @gl.public.write
    def open_claim(self, sla_id: int) -> dict:
        sla = self._sla(sla_id)
        if gl.message.sender_address != sla.consumer:
            raise _err("EXPECTED: only the named consumer may open a claim")
        now = _parse_ts(gl.message_raw["datetime"])
        last = int(sla.probe_count)
        if last == 0:
            raise _err("EXPECTED: no probes recorded")
        age = now - int(sla.last_probe_ts)
        if age > MAX_EVIDENCE_AGE_S:
            raise _err("EXPECTED: newest probe is stale; probe again before claiming")
        floor = max(int(sla.last_claimed_seq), last - WINDOW)
        n = last - floor
        if n < int(sla.min_probes):
            raise _err("EXPECTED: fewer unclaimed probes than min_probes")

        up = 0
        for seq in range(floor + 1, last + 1):
            p = self.probes[_slot(sla_id, seq)]
            if int(p.seq) != seq:
                raise _err("EXTERNAL: probe ring inconsistent")
            if p.outcome == UP:
                up += 1

        target = int(sla.target_bps)
        uptime_bps = (up * 10000) // n
        verdict = BREACHED if uptime_bps < target else MET
        credit = _credit_bps(target, uptime_bps) if verdict == BREACHED else 0

        claim_id = int(self.claim_count) + 1
        # effects before any downstream read: consume the evidence window first
        sla.last_claimed_seq = u256(last)
        self.claim_count = u256(claim_id)
        self.claims[u256(claim_id)] = Claim(
            sla_id=u256(sla_id),
            claimant=gl.message.sender_address,
            definition_hash=sla.definition_hash,
            first_seq=u256(floor + 1),
            last_seq=u256(last),
            probes=u256(n),
            up=u256(up),
            uptime_bps=u256(uptime_bps),
            target_bps=u256(target),
            verdict=verdict,
            credit_bps=u256(credit),
            opened_ts=u256(now),
            evidence_age_s=u256(age),
        )
        return {"claim_id": claim_id, "verdict": verdict, "uptime_bps": uptime_bps, "credit_bps": credit}

    # ------------------------------------------------------------------- views

    @gl.public.view
    def get_sla(self, sla_id: int) -> dict:
        s = self._sla(sla_id)
        return {
            "provider": s.provider.as_hex,
            "consumer": s.consumer.as_hex,
            "origin": s.origin,
            "probe_path": s.probe_path,
            "must_contain": s.must_contain,
            "expected_status": int(s.expected_status),
            "target_bps": int(s.target_bps),
            "min_probes": int(s.min_probes),
            "min_interval_s": int(s.min_interval_s),
            "definition_hash": s.definition_hash,
            "active": s.active,
            "probe_count": int(s.probe_count),
            "last_probe_ts": int(s.last_probe_ts),
            "last_claimed_seq": int(s.last_claimed_seq),
        }

    @gl.public.view
    def definition_hash(self, sla_id: int) -> str:
        return self._sla(sla_id).definition_hash

    @gl.public.view
    def get_probe(self, sla_id: int, seq: int) -> dict:
        s = self._sla(sla_id)
        last = int(s.probe_count)
        if seq < 1 or seq > last or seq <= last - WINDOW:
            raise _err("EXPECTED: probe not in the ring window")
        p = self.probes[_slot(sla_id, seq)]
        return {"seq": int(p.seq), "ts": int(p.ts), "outcome": p.outcome, "status": int(p.http_status)}

    @gl.public.view
    def window_uptime(self, sla_id: int) -> dict:
        """Uptime over the newest <=WINDOW probes (informational; claims use unclaimed probes)."""
        s = self._sla(sla_id)
        last = int(s.probe_count)
        n = min(last, WINDOW)
        up = 0
        for seq in range(last - n + 1, last + 1):
            if self.probes[_slot(sla_id, seq)].outcome == UP:
                up += 1
        bps = (up * 10000) // n if n > 0 else 0
        return {"probes": n, "up": up, "uptime_bps": bps, "last_probe_ts": int(s.last_probe_ts)}

    @gl.public.view
    def get_claim(self, claim_id: int) -> dict:
        key = u256(claim_id)
        if key not in self.claims:
            raise _err("EXPECTED: unknown claim_id")
        c = self.claims[key]
        return {
            "sla_id": int(c.sla_id),
            "claimant": c.claimant.as_hex,
            "definition_hash": c.definition_hash,
            "first_seq": int(c.first_seq),
            "last_seq": int(c.last_seq),
            "probes": int(c.probes),
            "up": int(c.up),
            "uptime_bps": int(c.uptime_bps),
            "target_bps": int(c.target_bps),
            "verdict": c.verdict,
            "credit_bps": int(c.credit_bps),
            "opened_ts": int(c.opened_ts),
            "evidence_age_s": int(c.evidence_age_s),
        }

    @gl.public.view
    def is_breached(self, claim_id: int) -> bool:
        key = u256(claim_id)
        return key in self.claims and self.claims[key].verdict == BREACHED

    @gl.public.view
    def credit_bps(self, claim_id: int) -> int:
        key = u256(claim_id)
        if key not in self.claims:
            raise _err("EXPECTED: unknown claim_id")
        return int(self.claims[key].credit_bps)

    @gl.public.view
    def claim_matches_definition(self, claim_id: int, expected_definition_hash: str) -> bool:
        key = u256(claim_id)
        return key in self.claims and self.claims[key].definition_hash == expected_definition_hash
