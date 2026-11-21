"""Where "full file access" stops.

The feature is a request to remove a restriction, so the tests are almost
entirely about the restrictions that remain. Two properties matter:

  1. OFF is what ships. It must behave exactly like the code that is already
     there — the home folder, nothing else — or turning the feature off becomes
     the dangerous state.
  2. Turning it ON must not hand over the machine. Credentials, the OS's own
     folders, browser password stores and this app's key file are refused even
     when the user granted the folder that contains them, because "I let it
     into my home directory" is not a decision to let it read an SSH key.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from actions import file_controller
from core import file_access as fa

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def home(tmp_path):
    root = tmp_path / "home"
    (root / "Documents").mkdir(parents=True)
    (root / "Documents" / "letter.txt").write_text("hello", encoding="utf-8")
    return root


@pytest.fixture()
def granted(tmp_path):
    root = tmp_path / "elsewhere"
    (root / "project").mkdir(parents=True)
    (root / "project" / "notes.md").write_text("notes", encoding="utf-8")
    return root


# ── the default is the state that ships ─────────────────────────────────────

def test_off_means_the_home_folder_and_nothing_else(home, granted):
    policy = fa.Policy(enabled=False, home=home)
    assert policy.check(home / "Documents" / "letter.txt").name == "letter.txt"
    with pytest.raises(fa.Denied):
        policy.check(granted / "project" / "notes.md")


def test_off_ignores_roots_that_were_configured(home, granted):
    """"Off" must not mean "whatever was configured last time". A user who
    turned it off expects the old behaviour, not the old access."""
    policy = fa.Policy(enabled=False, roots=(granted,), home=home)
    with pytest.raises(fa.Denied):
        policy.check(granted / "project" / "notes.md")


def test_a_missing_config_section_is_off(tmp_path, home):
    policy = fa.load(tmp_path / "nothing.json", home=home)
    assert policy.enabled is False
    assert policy.effective_roots() == (home,)


def test_a_malformed_config_is_off_not_on(home, tmp_path):
    """A settings problem must never be able to widen access."""
    for content in ("{not json", "[]", '{"file_access": "yes"}',
                    '{"file_access": {"enabled": "true"}}'):
        path = tmp_path / "settings.json"
        path.write_text(content, encoding="utf-8")
        policy = fa.load(path, home=home)
        assert policy.enabled is False, content


def test_only_a_literal_true_enables_it(home, tmp_path):
    """`"enabled": "true"` and `"enabled": 1` are not a decision the user made;
    they are a config file that was written by something else."""
    path = tmp_path / "settings.json"
    for value in ("true", 1, "yes", {}, [1]):
        path.write_text(json.dumps({"file_access": {"enabled": value}}),
                        encoding="utf-8")
        assert fa.load(path, home=home).enabled is False, value
    path.write_text(json.dumps({"file_access": {"enabled": True}}), encoding="utf-8")
    assert fa.load(path, home=home).enabled is True


def test_roots_that_cannot_be_resolved_are_dropped_not_guessed(home, tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"file_access": {
        "enabled": True,
        "roots": ["", None, 42, str(home)],
    }}), encoding="utf-8")
    policy = fa.load(path, home=home)
    assert policy.enabled is True
    assert policy.roots == (home.resolve(),)


# ── what is never allowed ───────────────────────────────────────────────────

@pytest.mark.parametrize("relative", [
    ".ssh", ".gnupg", ".aws", ".kube", ".docker", ".password-store",
    ".config/gh", ".config/gcloud",
])
def test_credential_folders_are_refused_inside_a_granted_root(home, relative):
    target = home / relative
    target.mkdir(parents=True, exist_ok=True)
    policy = fa.Policy(enabled=True, roots=(home,), home=home)
    with pytest.raises(fa.Denied) as err:
        policy.check(target / "anything.txt")
    assert "credentials" in str(err.value)


@pytest.mark.parametrize("name", ["id_rsa", "id_ed25519", ".netrc",
                                  ".git-credentials", "shadow", "sudoers"])
def test_credential_files_are_refused_wherever_they_are(home, name):
    policy = fa.Policy(enabled=True, roots=(home,), home=home)
    with pytest.raises(fa.Denied) as err:
        policy.check(home / "Documents" / name)
    assert "credentials" in str(err.value)


@pytest.mark.parametrize("path", [
    "/home/x/.config/google-chrome/User Data/Default/Login Data",
    "/home/x/.config/google-chrome/User Data/Default/Cookies",
    "/home/x/.mozilla/firefox/abc.default/key4.db",
])
def test_browser_password_and_cookie_stores_are_refused(path):
    policy = fa.Policy(enabled=True, roots=(Path("/"),), home=Path("/home/x"))
    with pytest.raises(fa.Denied) as err:
        policy.check(path)
    assert "password" in str(err.value) or "cookie" in str(err.value)


def test_windows_system_folders_are_refused_even_from_the_root(home):
    policy = fa.Policy(enabled=True, roots=(Path("C:/"),), home=home)
    for path in ("C:/Windows/System32/drivers/etc/hosts",
                 "C:/Windows/SysWOW64/anything.dll"):
        with pytest.raises(fa.Denied):
            policy.check(path)


def test_the_assistant_cannot_read_its_own_api_key(tmp_path, home):
    """A model that can read the key can spend the quota from a prompt
    injection, and the prompt injection is the whole threat model."""
    root = tmp_path / "app"
    (root / "config").mkdir(parents=True)
    (root / "config" / "api_keys.json").write_text("{}", encoding="utf-8")
    (root / "memory").mkdir()
    (root / "memory" / "long_term.json").write_text("{}", encoding="utf-8")

    policy = fa.Policy(enabled=True, roots=(root,), home=home)
    for rel in ("config/api_keys.json", "memory/long_term.json"):
        with pytest.raises(fa.Denied) as err:
            policy.check(root / rel)
        assert "own key or memory" in str(err.value)


# ── the boundary itself ─────────────────────────────────────────────────────

def test_a_path_outside_every_root_is_refused_with_the_list(home, granted):
    policy = fa.Policy(enabled=True, roots=(granted,), home=home)
    with pytest.raises(fa.Denied) as err:
        policy.check(home / "Documents" / "letter.txt")
    assert str(granted) in str(err.value), "the message must say what IS granted"


def test_climbing_out_of_a_root_with_dot_dot_is_refused(home, granted):
    policy = fa.Policy(enabled=True, roots=(granted / "project",), home=home)
    with pytest.raises(fa.Denied):
        policy.check(granted / "project" / ".." / ".." / "etc" / "passwd")


def test_a_symlink_cannot_smuggle_a_file_out_of_the_root(home, granted, tmp_path):
    """A link is a path that lies about where it goes. Every check is on the
    RESOLVED path, which is why the answer comes back resolved."""
    secret = tmp_path / "outside.txt"
    secret.write_text("not yours", encoding="utf-8")
    link = granted / "project" / "innocent.md"
    try:
        link.symlink_to(secret)
    except (OSError, NotImplementedError):
        pytest.skip("this filesystem cannot make symlinks")

    policy = fa.Policy(enabled=True, roots=(granted / "project",), home=home)
    with pytest.raises(fa.Denied):
        policy.check(link)


def test_the_check_returns_the_path_the_operation_must_use(home, granted):
    """A check is only meaningful if the operation then uses the same path."""
    policy = fa.Policy(enabled=True, roots=(granted,), home=home)
    returned = policy.check(granted / "project" / ".." / "project" / "notes.md")
    assert returned == (granted / "project" / "notes.md").resolve()
    assert returned.is_absolute()


def test_allows_is_check_without_the_exception(home, granted):
    policy = fa.Policy(enabled=True, roots=(granted,), home=home)
    assert policy.allows(granted / "project" / "notes.md") is True
    assert policy.allows(home / "Documents" / "letter.txt") is False


def test_a_path_that_cannot_be_resolved_is_refused(home, tmp_path):
    policy = fa.Policy(enabled=True, roots=(tmp_path,), home=home)
    # A NUL byte cannot be resolved on any platform; it must be a refusal, not
    # an exception of some other type escaping to the caller.
    with pytest.raises(fa.Denied):
        policy.check("\x00broken")


def test_describe_says_what_is_reachable(home, granted):
    assert "OFF" in fa.Policy(enabled=False, home=home).describe()
    on = fa.Policy(enabled=True, roots=(granted,), home=home)
    assert "ON" in on.describe() and str(granted) in on.describe()
    empty = fa.Policy(enabled=True, roots=(), home=home).describe()
    assert "no folder granted" in empty


# ── the promises as source checks ───────────────────────────────────────────

def test_the_policy_module_touches_no_files(log=None):
    """It decides; it does not act. The operations stay in file_controller,
    where every one of them already has an undo entry."""
    import ast
    src = Path(fa.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    opening = {"open", "write_text", "write_bytes", "unlink", "rmdir", "rmtree",
               "mkdir", "makedirs", "rename", "replace", "chmod"}
    used = {n.func.attr for n in ast.walk(tree)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
    used |= {n.func.id for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert not (opening & used - {"resolve"}), f"file operation in file_access.py: {opening & used}"


def test_the_deny_list_cannot_be_emptied_by_a_config_file():
    """There is no config key for the deny list, on purpose: a setting that
    switched it off would be the first thing a hostile instruction changed."""
    src = Path(fa.__file__).read_text(encoding="utf-8")
    assert "_DENY_NAMES" in src
    section = src[src.index("class Policy"):]
    assert "deny" not in section.split("def from_config")[1].split("def ")[0].lower()


# --------------------------------------------------------------------------
# Wiring: the policy is only real if the file controller asks it.
#
# The rule these tests defend is NOT "settings work". It is that a file
# operation's answer and the policy's answer are the same answer — because a
# boundary tested in isolation and a boundary in force are two different
# things, and only the second one protects anybody.
# --------------------------------------------------------------------------

@pytest.fixture()
def wired(tmp_path, monkeypatch):
    """file_controller reading a real settings.json we write."""
    def write_config(**section):
        cfg = tmp_path / "settings.json"
        cfg.write_text(json.dumps({"file_access": section}), encoding="utf-8")
        monkeypatch.setattr(
            file_controller, "_policy",
            lambda: fa.load(path=cfg, home=home_of(tmp_path)))
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: home_of(tmp_path)))
        return cfg

    home_of = lambda p: p / "home"                      # noqa: E731
    home_of(tmp_path).mkdir()
    monkeypatch.setattr(file_controller, "_LAST_DENIAL", {})
    return write_config


def test_off_refuses_a_folder_outside_home(wired):
    outside = wired().parent / "elsewhere"
    outside.mkdir()
    (outside / "x.txt").write_text("hi", encoding="utf-8")

    out = file_controller.delete_file(str(outside / "x.txt"))

    assert out.startswith("Access denied")
    assert (outside / "x.txt").exists()


def test_on_granted_root_lets_the_operation_through(wired):
    outside = wired().parent / "granted"
    outside.mkdir()
    (outside / "x.txt").write_text("hi", encoding="utf-8")
    wired(enabled=True, roots=[str(outside)])

    out = file_controller.list_files(str(outside))

    assert "x.txt" in out, out


def test_on_without_that_root_still_refuses(wired):
    granted = wired().parent / "granted"
    other = wired().parent / "other"
    granted.mkdir()
    other.mkdir()
    wired(enabled=True, roots=[str(granted)])

    out = file_controller.list_files(str(other))

    assert out.startswith("Access denied")


def test_the_refusal_quotes_the_rule_not_just_the_path(wired):
    """A denial that only says no is a puzzle. This one says which rule."""
    outside = wired().parent / "elsewhere"
    outside.mkdir()
    (outside / "x.txt").write_text("hi", encoding="utf-8")

    out = file_controller.delete_file(str(outside / "x.txt"))

    assert "outside your home" in out, out


def test_full_access_cannot_reach_an_ssh_key_inside_a_granted_root(wired):
    """The whole point of separating "may I" from "where": a grant is a place,
    not permission to read every secret that happens to live in it."""
    ssh = wired().parent / "home"                        # a root we grant
    (ssh / ".ssh").mkdir()
    (ssh / ".ssh" / "id_rsa").write_text("PRIVATE KEY", encoding="utf-8")
    wired(enabled=True, roots=[str(ssh)])

    out = file_controller.read_file(str(ssh / ".ssh" / "id_rsa"))

    assert out.startswith("Access denied")
    assert "PRIVATE KEY" not in out


def test_full_access_cannot_read_our_own_api_key(wired):
    """Reading the key is spending the user's quota under someone else's
    instructions — so the key is not a file the assistant may open."""
    key = wired().parent / "config" / "api_keys.json"
    key.parent.mkdir()
    key.write_text('{"gemini": "secret"}', encoding="utf-8")
    wired(enabled=True, roots=[str(key.parent.parent)])

    out = file_controller.read_file(str(key))

    assert out.startswith("Access denied")
    assert "secret" not in out


def test_a_broken_settings_file_leaves_access_where_it_was(wired):
    cfg = wired()
    cfg.write_text("{not json", encoding="utf-8")
    outside = cfg.parent / "elsewhere"
    outside.mkdir()
    (outside / "x.txt").write_text("hi", encoding="utf-8")

    out = file_controller.delete_file(str(outside / "x.txt"))

    assert out.startswith("Access denied")
    assert (outside / "x.txt").exists()


# --------------------------------------------------------------------------
# Turning it on: the one door, and who is allowed to open it.
# --------------------------------------------------------------------------

@pytest.fixture()
def real_config(tmp_path, monkeypatch):
    """A `memory.config_manager` pointed at a throw-away file."""
    from memory import config_manager

    cfg = tmp_path / "api_keys.json"
    monkeypatch.setattr(config_manager, "CONFIG_FILE", cfg)
    monkeypatch.setattr(config_manager, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config_manager, "_LAST_GOOD", {})
    return cfg


def test_saving_granted_folders_reads_back_as_that_policy(real_config, tmp_path):
    granted = tmp_path / "photos"
    granted.mkdir()

    assert fa.save([granted]) is True

    policy = fa.load(home=tmp_path / "home")
    assert policy.enabled is True
    assert policy.effective_roots() == (granted.resolve(),)


def test_saving_nothing_leaves_it_off(real_config, tmp_path):
    """Granting zero folders must not produce "on, with nowhere"."""
    assert fa.save([]) is False
    assert fa.load(home=tmp_path / "home").enabled is False


def test_a_file_is_not_a_folder_to_grant(real_config, tmp_path):
    afile = tmp_path / "notes.txt"
    afile.write_text("x", encoding="utf-8")

    assert fa.save([afile]) is False
    assert fa.load(home=tmp_path).enabled is False


def test_disabling_forgets_the_folders_it_had(real_config, tmp_path):
    """A list of folders waiting to come back is not a thing the user asked to
    keep when they turned the feature off."""
    granted = tmp_path / "photos"
    granted.mkdir()
    fa.save([granted])

    assert fa.disable() is True

    raw = json.loads(real_config.read_text(encoding="utf-8"))
    assert "file_access" not in raw


def test_the_grant_survives_a_missing_home(tmp_path, real_config):
    """A broken entry is dropped, the rest of the grant still stands."""
    good = tmp_path / "good"
    good.mkdir()
    fa.save([good, "/definitely/not/here", "", 42, None])

    policy = fa.load(home=tmp_path)
    assert policy.effective_roots() == (good.resolve(),)


def test_no_tool_may_grant_itself_access():
    """The door is a settings screen, not a function the model can call.

    This is the load-bearing test of the whole feature. `file_access.save` is
    a file-widening permission change; if any action or plugin imported it, a
    prompt injection could move the boundary instead of merely arguing with
    it. Scanned over the AST, not the text: a comment that mentions `save`
    must not fail the test, and an alias must not slip past it.
    """
    # `Policy` is deliberately NOT forbidden: building one changes nothing,
    # because the controller re-reads the grant from disk on every call. The
    # two functions that write the grant are the door, and only they are.
    forbidden = {"save", "disable"}
    offenders = []
    for folder in ("actions", "plugins"):
        for path in (ROOT / folder).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            # Every name this file could reach the module by — an alias is the
            # obvious way past a scan that only looks for the plain name.
            aliases = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    if node.module == "core.file_access":
                        if {a.name for a in node.names} & forbidden:
                            offenders.append(f"{path}:{node.lineno} imports {sorted(forbidden)}")
                        aliases |= {a.asname or a.name for a in node.names
                                    if a.name == "file_access"}
                    elif node.module == "core":
                        aliases |= {a.asname or a.name for a in node.names
                                    if a.name == "file_access"}
                elif isinstance(node, ast.Import):
                    for a in node.names:
                        if a.name == "core.file_access":
                            aliases.add(a.asname or "core")
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                if (isinstance(func, ast.Attribute) and func.attr in forbidden
                        and _reaches_module(func.value, aliases)):
                    offenders.append(f"{path}:{node.lineno} calls {func.attr}()")
    assert not offenders, offenders


def _reaches_module(node, aliases: set[str]) -> bool:
    """`fa.save`, `core.file_access.save`, `mod.save` — any chain rooted at an
    alias of this module."""
    while isinstance(node, ast.Attribute):
        node = node.value
    return isinstance(node, ast.Name) and node.id in aliases


def test_the_default_config_path_is_the_settings_file_that_exists():
    """Not a file we invented: the one setup already writes."""
    path = fa._default_config_path()
    assert path.name == "api_keys.json"
    assert path.parent.name == "config"


def test_an_empty_grant_is_not_the_current_folder(real_config, tmp_path, monkeypatch):
    """`Path("")` is `Path(".")` in Python. An empty entry must not silently
    grant whatever directory the app happened to start in."""
    launched_from = tmp_path / "launch-dir"
    launched_from.mkdir()
    monkeypatch.chdir(launched_from)
    good = tmp_path / "good"
    good.mkdir()

    fa.save([good, "", "   ", None, 3.5])

    roots = fa.load(home=tmp_path).effective_roots()
    assert launched_from.resolve() not in roots
    assert roots == (good.resolve(),)


def test_save_accepts_path_objects_like_a_settings_screen_would(real_config, tmp_path):
    """A folder picker hands back a Path; refusing it would be a silent no-op
    from the UI's point of view."""
    good = tmp_path / "picked"
    good.mkdir()

    assert fa.save([good]) is True
    assert fa.load(home=tmp_path).effective_roots() == (good.resolve(),)


# --------------------------------------------------------------------------
# The row that makes the door reachable.
#
# Tested with Qt stubbed, like `tests/test_notify.py`: a folder dialog cannot
# be clicked from here, so the picker is injected. What is under test is the
# pair — did the user's choice reach the config, and does the button report the
# policy that is actually in force rather than the one it hoped to write.
# --------------------------------------------------------------------------

class _FakeButton:
    def __init__(self):
        self.text = ""
        self.tooltip = ""
        self.style = ""

    def setText(self, value):
        self.text = value

    def setToolTip(self, value):
        self.tooltip = value

    def setStyleSheet(self, value):
        self.style = value

    def setFont(self, value):
        pass


@pytest.fixture()
def row(monkeypatch):
    """`ui/file_access_row.py` with PyQt6 and the theme stubbed out."""
    import importlib.util
    import sys
    import types

    gui = types.ModuleType("PyQt6.QtGui")
    gui.QFont = lambda *a, **k: None
    widgets = types.ModuleType("PyQt6.QtWidgets")
    widgets.QPushButton = _FakeButton
    theme = types.ModuleType("ui.theme")
    theme.C = types.SimpleNamespace(RED="#f00", TEXT="", TEXT_DIM="", WHITE="",
                                    BORDER="", BORDER_B="")

    saved = {n: sys.modules.get(n) for n in
             ("PyQt6", "PyQt6.QtGui", "PyQt6.QtWidgets", "ui.theme")}
    sys.modules.update({"PyQt6": types.ModuleType("PyQt6"), "PyQt6.QtGui": gui,
                        "PyQt6.QtWidgets": widgets, "ui.theme": theme})
    spec = importlib.util.spec_from_file_location(
        "file_access_row", ROOT / "ui" / "file_access_row.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        yield module
    finally:
        for name, value in saved.items():
            if value is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = value


def test_the_row_turns_on_with_the_folder_the_user_picked(row, real_config, tmp_path):
    granted = tmp_path / "photos"
    granted.mkdir()
    button = _FakeButton()

    on = row.toggle(button, picker=lambda: [str(granted)], home=tmp_path)

    assert on is True
    assert fa.load(home=tmp_path).effective_roots() == (granted.resolve(),)
    assert "ON" in button.text


def test_the_row_turns_off_without_asking_where(row, real_config, tmp_path):
    """Off is not a question. A picker opened on the way to OFF would be a
    dialog that changes nothing."""
    granted = tmp_path / "photos"
    granted.mkdir()
    fa.save([granted])
    button = _FakeButton()
    asked = []
    row.toggle(button, picker=lambda: asked.append(1) or [], home=tmp_path)

    assert asked == []
    assert fa.load(home=tmp_path).enabled is False
    assert "OFF" in button.text


def test_a_cancelled_picker_changes_nothing(row, real_config, tmp_path):
    button = _FakeButton()

    assert row.toggle(button, picker=lambda: [], home=tmp_path) is False
    assert fa.load(home=tmp_path).enabled is False


def test_the_button_reports_the_policy_not_the_optimism(row, real_config, tmp_path):
    """`save` saying True is not proof. The button must repaint from a read."""
    button = _FakeButton()
    row.toggle(button, picker=lambda: ["/definitely/not/here"], home=tmp_path)

    assert "OFF" in button.text, button.text


def test_the_row_never_grants_more_than_what_was_picked(row, real_config, tmp_path):
    """The drawer passes paths straight to the policy — it does not add home,
    temp or the program folder "for convenience"."""
    granted = tmp_path / "photos"
    granted.mkdir()
    row.toggle(_FakeButton(), picker=lambda: [str(granted)], home=tmp_path)

    raw = json.loads(real_config.read_text(encoding="utf-8"))
    assert raw["file_access"]["roots"] == [granted.resolve().as_posix()]
