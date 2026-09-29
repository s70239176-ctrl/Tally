"""Forged-leader and pickling tests for the probe validator.

`direct_vm.run_validator` feeds the validator a leader result of our choosing while the
validator re-observes the (mocked) endpoint itself. A well-formed but substantively
false leader result must be rejected.
"""
import cloudpickle
import pytest


def _probe_up(env):
    sid = env.register()
    env.up()
    env.probe(sid)
    return sid


def _validate(env, leader_result):
    return env.vm.run_validator(leader_result=leader_result)


def test_honest_leader_accepted(env):
    _probe_up(env)
    assert _validate(env, {"outcome": "UP", "status": 200}) is True


def test_forged_up_rejected_when_validator_sees_down(env):
    _probe_up(env)
    env.down(503)
    assert _validate(env, {"outcome": "UP", "status": 200}) is False


def test_forged_up_rejected_when_validator_cannot_reach(env):
    _probe_up(env)
    env.unreachable()
    assert _validate(env, {"outcome": "UP", "status": 200}) is False


def test_forged_down_rejected_when_validator_sees_up(env):
    _probe_up(env)
    assert _validate(env, {"outcome": "DOWN", "status": 503}) is False


def test_forged_down_rejected_when_validator_sees_200_wrong_body(env):
    _probe_up(env)
    env.down(200, "maintenance")
    # honest classification is DOWN; a leader claiming UNREACHABLE is not equivalent
    assert _validate(env, {"outcome": "UNREACHABLE", "status": 0}) is False
    assert _validate(env, {"outcome": "DOWN", "status": 200}) is True


def test_down_vs_unreachable_not_equivalent(env):
    _probe_up(env)
    env.unreachable()
    assert _validate(env, {"outcome": "DOWN", "status": 503}) is False
    assert _validate(env, {"outcome": "UNREACHABLE", "status": 0}) is True


def test_differing_error_status_is_equivalent(env):
    _probe_up(env)
    env.down(502)
    assert _validate(env, {"outcome": "DOWN", "status": 500}) is True


@pytest.mark.parametrize("forged", [
    {"outcome": "UP", "status": True},               # bool where int expected
    {"outcome": "UP", "status": 200.0},              # float where int expected
    {"outcome": "UP", "status": "200"},              # decimal string
    {"outcome": "UP", "status": "0xC8"},             # hex string
    {"outcome": "UP", "status": -1},                 # negative
    {"outcome": "UP", "status": 600},                # out of range
    {"outcome": "UP", "status": 201},                # UP but not the expected status
    {"outcome": "up", "status": 200},                # wrong-case enum
    {"outcome": "MAYBE_UP", "status": 200},          # unknown enum
    {"outcome": True, "status": 200},                # truthy non-string
    {"outcome": "UP"},                               # missing field
    {"status": 200},                                 # missing field
    {"outcome": "UP", "status": 200, "safe": True},  # extra field
    ["UP", 200],                                     # list instead of dict
    "UP",                                            # bare string
    None,
    {"outcome": "DOWN", "status": 0},                # DOWN needs a real status
    {"outcome": "UNREACHABLE", "status": 503},       # UNREACHABLE must carry status 0
])
def test_malformed_leader_results_rejected(env, forged):
    _probe_up(env)
    assert _validate(env, forged) is False


def test_leader_error_is_rejected(env):
    _probe_up(env)
    assert env.vm.run_validator(leader_error=Exception("boom")) is False


def test_probe_is_picklable(env):
    _probe_up(env)
    _, leader_fn, validator_fn = env.vm._captured_validators[-1]
    cloudpickle.loads(cloudpickle.dumps(leader_fn))
    cloudpickle.loads(cloudpickle.dumps(validator_fn))


def test_no_state_change_when_probe_reverts(env):
    sid = env.register()
    env.up()
    env.probe(sid)
    before = env.c.get_sla(sid)
    with env.vm.expect_revert("cooldown"):
        env.probe(sid, dt=1)
    assert env.c.get_sla(sid) == before
