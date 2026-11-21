"""`jarvis://` — the one address that reaches a running assistant.

WHY THIS EXISTS
    The app now has four ways to be started and no way to be REACHED. Every
    integration an operating system offers beyond a launch icon is an address:
    a browser link, a shortcut in another program, a Stream Deck button, a
    notification handler, a shell alias. Without a scheme, all of them can only
    do the one thing the tray already does — bring the window forward — and
    anything that should carry a REQUEST (say this, open that) has no way to say
    what it wants.

THE RULE THIS MODULE FOLLOWS
    A URL is UNTRUSTED INPUT. It arrives from a browser, a chat message, a
    web page, an address bar — anything that can call `open`. The whole class of
    bug here is an attacker writing `jarvis://run?cmd=...` and having the
    assistant execute it. So:

      * there is NO verb that runs a command, opens a file by path, or touches
        the config. The vocabulary is what the TRAY can already do, plus one:
        `summon`, `hide`, `ask`.
      * `ask` is the only one that carries text, and the text is bounded,
        single-purpose, and handed to the SESSION as a user turn — the same
        place a typed message or a spoken sentence goes. It cannot pick a tool,
        name a file, or set a flag.
      * every parameter is validated and REJECTED rather than repaired: an
        unknown verb, a query on a verb that takes none, text longer than the
        cap, control characters, NUL bytes. Nothing is silently truncated into
        something that means a different thing.
      * a URL with userinfo (`jarvis://user:pass@…`), a port, or a fragment is
        refused. None of them mean anything here, and accepting them quietly is
        how a parser and a caller end up disagreeing about what was asked.

WHY IT IS PURE
    Nothing in this file opens a socket, writes a file or needs Qt. `parse()`
    turns a string into a `Request` or raises `Rejected` with a sentence fit to
    show a user; `dispatch()` calls the handler the caller supplies. That is
    what makes the security properties checkable on a machine with no browser
    and no display — which is every CI runner here.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

SCHEME = "jarvis"

# The whole vocabulary. Deliberately tiny, and deliberately the same set of
# things a person could already do without this file existing.
VERBS = ("summon", "hide", "ask")

# `ask` carries speech, not structure. 500 characters is two or three sentences
# — long enough for "remind me to call the dentist at four", short enough that
# nothing can be smuggled in behind a legitimate-looking question.
MAX_TEXT = 500

# Refused explicitly rather than ignored. Each of these parses to something
# Python accepts and a human would not expect.
_FORBIDDEN_PARTS = ("username", "password", "port", "fragment")


class Rejected(ValueError):
    """A URL this scheme does not accept. The message is shown to the user."""


@dataclass(frozen=True)
class Request:
    """What a URL asked for, validated.

    `verb` is always one of `VERBS`; `text` is only ever set for `ask`. A
    Request cannot express anything else — there is no field to put a path, a
    command or a setting in, which is the point: the type is the policy.
    """

    verb: str
    text: str = ""

    def as_dict(self) -> dict:
        return {"verb": self.verb, "text": self.text}


def parse(url: str) -> Request:
    """Turn `jarvis://…` into a Request, or raise `Rejected`.

    The two shapes accepted:

        jarvis://summon            (also jarvis:summon — see `_split`)
        jarvis://ask?text=...      text is required, url-encoded
        jarvis://hide

    A trailing slash is allowed; anything else in the path is not.
    """
    if not isinstance(url, str):
        raise Rejected("not a link")
    raw = url.strip()
    if not raw:
        raise Rejected("empty link")

    # Case-insensitive scheme: `JARVIS://summon` arrives from a browser that
    # normalised it, and refusing the upper case would be a coin flip for the
    # user over a detail nobody controls.
    if raw.lower().startswith(f"{SCHEME}:"):
        if not raw.lower().startswith(f"{SCHEME}://"):
            # `jarvis:summon` — a browser will pass this through. Handled here
            # rather than by rewriting the string, so what was parsed is what
            # arrived.
            rest = raw[len(SCHEME) + 1:]
            raw = f"{SCHEME}://{rest}"

    try:
        parts = urlsplit(raw)
    except ValueError as e:
        raise Rejected(f"that link is malformed ({e})") from None

    if parts.scheme.lower() != SCHEME:
        raise Rejected(f"not a {SCHEME}: link")

    for field in _FORBIDDEN_PARTS:
        if getattr(parts, field, None):
            raise Rejected(f"a {SCHEME}: link cannot carry a {field}")

    verb = parts.netloc.strip().lower()
    if not verb:
        raise Rejected("the link does not say what to do")
    if verb not in VERBS:
        raise Rejected(
            f"unknown action '{verb}' — this assistant understands: "
            + ", ".join(VERBS))
    if parts.path not in ("", "/"):
        raise Rejected(f"'{verb}' does not take a path")

    query = parse_qs(parts.query, keep_blank_values=True)
    if verb != "ask":
        if query:
            raise Rejected(f"'{verb}' does not take any parameters")
        return Request(verb)

    if set(query) - {"text"}:
        unknown = sorted(set(query) - {"text"})[0]
        raise Rejected(f"'ask' does not take a '{unknown}' parameter")
    text = (query.get("text") or [""])[0]
    if len(query.get("text") or []) > 1:
        raise Rejected("'ask' takes one text parameter")
    text = _clean_text(text)
    return Request(verb, text)


def _clean_text(text: str) -> str:
    """Validate the only free-form thing this scheme accepts.

    Control characters are refused, not stripped: a NUL or an escape sequence
    removed from the middle of a sentence changes its meaning, and the caller
    deserves to know their link was wrong rather than to have it edited.
    """
    if not text:
        raise Rejected("'ask' needs something to say")
    if len(text) > MAX_TEXT:
        raise Rejected(f"that text is too long ({len(text)} > {MAX_TEXT} characters)")
    if any(ch < " " or ch == "\x7f" for ch in text):
        raise Rejected("that text contains control characters")
    return text


def dispatch(request: Request, *, summon, hide, ask) -> bool:
    """Run a parsed Request through the caller's three handlers.

    `ask` returns True when the request was actually delivered — the session may
    not be up yet, and a link that said something into a microphone nobody is
    reading must not report success. `dispatch` passes that answer back for the
    same reason: a shell command or a browser popup that closes with no message
    leaves the user unable to tell "it worked" from "nothing happened".
    """
    if request.verb == "summon":
        summon()
        return True
    if request.verb == "hide":
        hide()
        return True
    if request.verb == "ask":
        return bool(ask(request.text))
    raise Rejected(f"unknown action '{request.verb}'")     # unreachable: parse()


# ── registering the scheme with the operating system ────────────────────────
#
# Every platform stores this somewhere different, and every one of them has a
# detail that fails silently if it is wrong. The text builders are separate
# functions so the exact bytes can be asserted without writing to a registry.

def windows_command(script: str, python: str | None = None) -> str:
    r"""The `shell\open\command` value, quoted.

    `"%pythonw%" "%script%" "%1"` — `%1` is the URL, in quotes, and the
    interpreter is `pythonw.exe` where it exists so a link does not flash a
    console. Unquoted, `C:\Program Files\...` splits at the first space and the
    registration points at a program that does not exist.
    """
    import sys
    from pathlib import Path

    exe = python or sys.executable
    if Path(exe).name.lower() == "python.exe":
        windowed = Path(exe).parent / "pythonw.exe"
        if windowed.exists():
            exe = str(windowed)
    return f'"{exe}" "{script}" "%1"'


def linux_desktop_text(script: str, python: str | None = None,
                       name: str = "J.A.R.V.I.S") -> str:
    r"""A `.desktop` file with `MimeType=x-scheme-handler/jarvis` and `%u`.

    `%u` — a single URL — is what the spec requires for a scheme handler;
    `%U` (a list) would be accepted by the parser and then passed as several
    arguments, and `%f` (a file) means the URL arrives as a path with the
    scheme stripped. Each of those is a handler that starts but cannot read
    what it was given.
    """
    from core.autostart import _exec_value

    exe = _exec_value(script, python, args=("%u",))
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={name}\n"
        f"Exec={exe}\n"
        "Terminal=false\n"
        "NoDisplay=true\n"          # a handler is not something to launch from a menu
        f"MimeType=x-scheme-handler/{SCHEME};\n"
        "Categories=Utility;\n"
    )


def mac_info_plist(app_name: str = "JARVIS") -> str:
    """The `CFBundleURLTypes` fragment an `.app` needs to receive the scheme.

    Returned as text to be merged into the bundle's `Info.plist`; the caller
    owns that file. `CFBundleURLName` must be unique across the system, which is
    why it is a reverse-DNS identifier rather than the scheme itself.
    """
    return (
        "<key>CFBundleURLTypes</key>\n"
        "<array><dict>\n"
        f"  <key>CFBundleURLName</key><string>com.jarvis.assistant</string>\n"
        "  <key>CFBundleURLSchemes</key>\n"
        f"  <array><string>{SCHEME}</string></array>\n"
        f"  <key>CFBundleTypeRole</key><string>Viewer</string>\n"
        f"  <key>CFBundleURLIconFile</key><string>{app_name}</string>\n"
        "</dict></array>\n"
    )
