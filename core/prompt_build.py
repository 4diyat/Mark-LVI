"""What the model is told about itself, as functions instead of as strings.

WHY THIS IS A MODULE
    Three of these functions — `describe_tools`, `describe_limits`,
    `render` — lived in `main.py` and had **no tests at all**, because reaching
    them meant importing the Live SDK, sounddevice, numpy and Qt. Yet they build
    the only description the model ever gets of its own abilities: a bug here is
    the assistant claiming it can see on a machine with no camera, or refusing
    to hear on a machine with a working microphone. Both of those are in this
    file's history.

    So the wording moved out and the wiring stayed in `main.py`, which is the
    same trade `core/session_policy.py` made: the part that DECIDES is separate
    from the part that holds a session.

WHAT IS PURE AND WHAT IS NOT
    Everything here takes its inputs as arguments and returns a string or a
    list. `describe_limits` does NOT go looking for the platform's opinion — the
    caller passes it in. The one thing that needs the machine is
    `core/platform_support.describe_for_model()`, and keeping it outside means
    this file can be tested on a machine that is not the one it describes.

THE ONE IDEA WORTH KEEPING
    The model's self-knowledge is DERIVED, never written down twice. The tool
    list comes from the registries that were just discovered; the limits come
    from how this build was assembled. Add a plugin and the prompt follows;
    remove a camera and the prompt stops promising sight. A hand-written list
    would be right for a week.
"""
from __future__ import annotations


def tool_name(declaration) -> str:
    """The name of a tool declaration, whichever shape it has.

    Declarations arrive as dicts from the registries and as objects from the
    provider SDK. The same expression was written out seven times in
    `_build_config`, and one copy drifting is how a tool gets withheld from
    `_names` but not from the wire.
    """
    if isinstance(declaration, dict):
        return declaration.get("name") or ""
    return getattr(declaration, "name", "") or ""


def describe_tools(declarations) -> str:
    """One line per capability, straight from the live declarations.

    Derived rather than written down: whatever the user has installed is what
    the model is told it can do. Adding a plugin extends this by itself, and
    removing one stops the model from claiming an ability it no longer has.
    """
    lines = []
    for d in declarations or ():
        try:
            name = tool_name(d)
            desc = (d.get("description") if isinstance(d, dict)
                    else getattr(d, "description", "")) or ""
        except Exception:                    # noqa: BLE001 — one odd decl
            continue
        if not name:
            continue
        desc = " ".join(str(desc).split())
        lines.append(f"- {name}: {desc[:150]}" if desc else f"- {name}")
    return "\n".join(lines)


def describe_limits(has_vision: bool, has_mic: bool,
                    platform_lines=()) -> str:
    """The other half of self-knowledge: what is out of reach, and why.

    `platform_lines` is what `core.platform_support.describe_for_model()` says
    about the host — passed IN so this function says the same thing on every
    machine and can be tested for what it says rather than for what it happens
    to run on.
    """
    out = [
        "- Anything not listed above is outside your reach. Say so in one clause "
        "and offer the nearest thing you can actually do — never mime an action "
        "you cannot take, and never report a result you did not get.",
        "- You act on this machine only. You cannot reach the user's other "
        "devices, accounts or hardware except through the tools listed above.",
        "- You remember what is in the memory block and what has been said this "
        "session. Anything else you were told before is gone unless it was saved.",
    ]
    # What the PLATFORM forbids comes before what the build lacks.
    #
    # On Wayland, and on a macOS without Accessibility, the keyboard, mouse and
    # screen are simply not available to any program — and the APIs report
    # success anyway. A model that does not know this reports clicks that never
    # happened, which is how "it does not work properly on Linux" was described
    # for a long time without anybody being able to name the failing part.
    out.extend(platform_lines or ())

    if has_vision:
        out.append(
            "- Your sight is not continuous. You see nothing until you call a "
            "vision tool, and then only that single frame at that moment — you "
            "cannot watch, monitor or notice something changing on screen.")
    else:
        out.append("- You have no sight at all in this build.")
    if has_mic:
        out.append(
            "- You hear nothing while the microphone is muted, and you cannot "
            "unmute it yourself.")
    else:
        # The branch that did not exist. Without it, a machine with no
        # microphone produced a prompt that said NOTHING about it, and the model
        # behaved as if it could hear — answering "I did not catch that" forever
        # while the user spoke into a device that was not there.
        out.append(
            "- The computer microphone is unavailable. A paired remote device "
            "may still send audio; respond normally if audio arrives. Do not "
            "pretend to hear from the computer microphone. Text remains available.")
    return "\n".join(out)


def render(template: str, values: dict) -> str:
    """Fill {tokens} in the prompt template.

    A plain replace rather than `str.format`: the file is meant to be edited by
    hand, and a stray brace in someone's own wording must never take the app
    down at startup.
    """
    out = template or ""
    for key, val in values.items():
        out = out.replace("{" + key + "}", str(val))
    return out


def identity_block(assistant_name: str, user_name: str = "") -> str:
    """Who the assistant is, and how it addresses the user.

    The address rule is stated as a PRINCIPLE rather than a two-language
    lookup, because address form is a property of the language being spoken and
    the model already knows the respectful register of whatever language it is
    in. A hardcoded pair of words is wrong in every third language.
    """
    # Strip BEFORE the fallback: a config value of "   " is not a name, and
    # `or` on the raw string treats it as one, producing "Your name is .".
    name = (assistant_name or "").strip() or "JARVIS"
    if user_name:
        address = f"ADDRESS: Always call the user '{user_name}'."
    else:
        address = ('ADDRESS: Address the user with the ordinary respectful form '
                   'for a superior in the language you are currently speaking — '
                   '"sir" in English, its everyday equivalent in any other '
                   'language. Never an archaic or aristocratic form, and never '
                   'the form from a different language than the one you are '
                   'speaking in this sentence.')
    return (f"[IDENTITY]\nYour name is {name}. Always refer to yourself as {name}."
            f"\n{address}\n\n")


def withhold(declarations, caps):
    """Drop the tools an engine cannot serve, and say what was dropped.

    An engine that cannot do something is not offered the tool for it. This is
    why capabilities are data rather than a pile of conditions: the SAME
    filtering feeds `describe_limits`, so an engine with no eyes ends up with
    the model being TOLD it cannot see. Without that it would be handed a tool
    it cannot serve, call it, get nothing back, and describe a screen it never
    received.

    `caps is None` means Gemini Live, which skips all of it — the declaration
    list is then byte-for-byte what it has always been.

    Returns `(declarations, blocked_count)`.
    """
    if caps is None:
        return list(declarations or ()), 0

    blocked = set()
    if not caps.get("vision"):
        blocked |= {"screen_process", "close_camera"}
    if not caps.get("tools"):
        # No tools at all: withhold every one of them. Naming them from the
        # list itself rather than from a constant means a plugin added later is
        # withheld too, instead of slipping through on a stale allow-list.
        blocked = {tool_name(d) for d in (declarations or ())}
    if not blocked:
        return list(declarations or ()), 0
    kept = [d for d in (declarations or ()) if tool_name(d) not in blocked]
    return kept, len(blocked)


def time_block(now) -> str:
    """The date and time, as the prompt states it.

    `now` is passed in: a function that reads the clock cannot be tested for
    what it says, and this string is the model's only way to answer "what time
    is it" without calling a tool.
    """
    stamp = now.strftime("%A, %B %d, %Y — %I:%M %p")
    return ("[CURRENT DATE & TIME]\n"
            f"Right now it is: {stamp}\n"
            "Use this to calculate exact times for reminders.\n\n")


__all__ = ["describe_limits", "describe_tools", "identity_block", "render",
           "time_block", "tool_name", "withhold"]
