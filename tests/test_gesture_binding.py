"""Board 15's gesture binding policy, driven with no store and no UI."""
from core.gesture_binding import (ACTIONS, CLICK, DEFAULT_BINDINGS, FIST,
                                  GESTURES, INTERFACE_CALL, MEDIA_PAUSE,
                                  BindingDecision, current, is_action,
                                  is_gesture, next_action, request, summary)


def test_the_gesture_set_is_the_artboard_three():
    assert GESTURES == ("open_palm", "pinch", "fist")


def test_the_action_set_is_frozen_and_known():
    for action in (INTERFACE_CALL, CLICK, MEDIA_PAUSE):
        assert is_action(action)
    assert "bogus" not in ACTIONS


def test_is_gesture_and_is_action_reject_the_other_kind():
    assert is_gesture("open_palm")
    assert not is_gesture("open_palm_x")
    assert is_action(CLICK)
    assert not is_action(FIST)


def test_the_default_bindings_match_the_artboard():
    assert DEFAULT_BINDINGS == {
        "open_palm": INTERFACE_CALL, "pinch": CLICK, "fist": MEDIA_PAUSE}


def test_next_action_cycles_and_starts_at_the_top():
    assert next_action(INTERFACE_CALL) == CLICK
    assert next_action(MEDIA_PAUSE) == ACTIONS[3]
    # An unknown current action starts the cycle at the first real action.
    assert next_action("bogus") == ACTIONS[0]


def test_current_reads_the_store_and_collapses_unknowns():
    def read():
        return {"open_palm": CLICK, "pinch": "bogus", "fist": MEDIA_PAUSE}
    out = current(read)
    assert out["open_palm"] == CLICK
    assert out["pinch"] == DEFAULT_BINDINGS["pinch"]  # bogus -> default


def test_current_falls_back_when_the_read_raises():
    def boom():
        raise RuntimeError("no config")
    assert current(boom) == dict(DEFAULT_BINDINGS)


def test_current_falls_back_when_the_read_is_not_a_dict():
    assert current(lambda: ["not", "a", "dict"]) == dict(DEFAULT_BINDINGS)


def test_a_real_change_is_allowed_and_changed():
    decision = request("fist", MEDIA_PAUSE, CLICK)
    assert decision.allowed
    assert decision.changed
    assert decision.desired == CLICK


def test_a_re_pick_of_the_current_action_is_a_noop():
    decision = request("fist", MEDIA_PAUSE, MEDIA_PAUSE)
    assert decision.allowed
    assert not decision.changed


def test_an_unknown_action_is_refused_and_does_not_claim_the_new_value():
    decision = request("fist", MEDIA_PAUSE, "bogus")
    assert not decision.allowed
    assert not decision.changed
    assert decision.desired == MEDIA_PAUSE


def test_an_unknown_gesture_is_refused():
    decision = request("bogus", CLICK, MEDIA_PAUSE)
    assert not decision.allowed


def test_summary_names_the_gesture_and_its_action():
    text = summary("fist")
    assert "fist" in text or "kepalan" in text
    assert MEDIA_PAUSE not in text or "jeda media" in text


def test_the_decision_carries_the_gesture():
    decision = request("fist", MEDIA_PAUSE, CLICK)
    assert decision.gesture == "fist"


def test_the_repr_states_the_decision():
    text = repr(BindingDecision("fist", MEDIA_PAUSE, CLICK, True, "x"))
    assert "BindingDecision" in text
