# What the mockup does not draw, and what happened to it

**Read this before adding a surface to `ui/`.** The design sheet
(`jarvis-design-system.html`, built by `build.py`) is twelve artboards, and
nothing else exists in this build. Everything that used to be in the app but is
not on one of those boards was **deleted**, not hidden, not disabled and not
left in place "for later". This file is the record: what it was, why it is
gone, and how to get it back.

The commit this file describes is the one that carries it. To compare against
the last build with a window:

```bash
git diff 376909f1..HEAD --stat -- ui/            # what changed, file by file
git show 376909f1:ui/window.py                   # any deleted file, in full
git checkout 376909f1 -- ui/setup_overlay.py     # bring ONE file back
```

`376909f1` is the merge commit of PR #56 — the last commit where the app had a
main window. Nothing was moved to an archive directory, by request: the only
copy of the old code is in git.

---

## The twelve boards, and the only surfaces they justify

| # | Board | What it draws | Module |
|---|---|---|---|
| 1 | Orb overlay — Siaga & area klik | a ring on the desktop, click-through outside | `ui/orb_overlay.py` |
| 2 | Toast — antrean & batas harian | three toasts, the rest counted | `ui/toast_queue.py` |
| 3 | Command bar — Ctrl+Space | one line, Esc gives focus back | `ui/command_bar.py` |
| 4 | Orb overlay — interaksi & status | the same ring, five states | `ui/orb_paint.py` |
| 5 | Panel baki sistem | the 460×660 tray panel: three segments, four quick actions with chords, today's suggestion, permissions, one line to type in | `ui/tray_panel.py`, `ui/tray_pages.py`, `ui/tray_panel_model.py` |
| 6 | Overlay suara + kamera gestur | listening overlay, gesture camera tile | **proposal — see below** |
| 23 | Fokus — toast ditahan | held notifications, counted | `ui/toast_queue.py` |
| 24 | Senyap — orb memudar | the orb dimmed, still there | `ui/orb_overlay.py` |
| 25 | Risiko: konfirmasi | amber risk dialog, trusted UI | `ui/confirm_banner.py` |
| 26 | Riwayat tugas + Urungkan | task history with undo, audit tail, export and clear | `ui/tray_panel.py` (history page) |
| 27 | Izin & Privasi | three indicators, four explicit permissions, guest mode, erase | `ui/tray_panel.py` (privacy page) |
| 28 | Tema terang — panel baki | the same panel, light palette | `ui/tray_pages.py` (`PALETTES["light"]`) |

Plus the surfaces the owner explicitly kept that no board draws: the **face
bubble** (`ui/face_bubble.py`, `ui/face_canvas.py`) and the **orchestrator**
(`ui/shell.py`, `ui/lifecycle.py`, `ui/ambient_shell.py`).

### The tray panel, and what each part of it really does

`ui/tray_panel_model.py` reads the world; `ui/tray_pages.py` is the geometry and
the two palettes; `ui/tray_panel.py` is lifecycle, dispatch and paint;
`ui/tray_panel_wiring.py` says which function is behind which control. A left
click on the tray icon opens it; the right click still opens the old `QMenu`,
because that menu is the fallback when the panel cannot be built.

Four things are drawn but NOT fully backed, and each says so on screen rather
than by omission:

| Control | What it does today |
|---|---|
| **Susun jendela** | Refused out loud. There is no window-snapping code in this tree — it was never written. The row is on the artboard, so the row is drawn; pressing it explains that and points at the chord. |
| **Mode tamu** | Refused out loud. Guest mode needs every surface to stop reading memory; nothing does that yet, so the switch changes nothing and says so. |
| **Dikte** | Works, but it is a SIX-SECOND hold released on a timer — a button cannot express "until I let go". The press-and-hold version is the chord on the same row. |
| **Cari berkas** | Opens the command bar with `Cari berkas ` already typed instead of searching: the search needs a query, and the bar is where the user already types one. |

The chords printed on the rows (`Ctrl+Shift+S`, `Ctrl+Win`, `Ctrl+Shift+F`,
`Ctrl+Shift+J`) are the ARTBOARD'S. Only `Ctrl+Shift+J` (summon) and `Ctrl+Space`
(command bar) are actually bound by this program; the other three are printed
labels, not registered hotkeys. A chord on a row is not a promise the OS owns it.

The suggestion row is empty in this build and says "Belum ada saran hari ini."
`core.suggestion_quota` counts suggestions; nothing generates them yet.

**Hapus semua data lokal** erases the audit log — the record of what the
assistant did. It does not touch `config/api_keys.json`, the conversation
history files, or anything already sent to the model. **Hapus riwayat** clears
the undo stack only. Two buttons for two stores, deliberately.

---

## Deleted: the window and everything inside it

### `ui/window.py` — 3,797 lines

`MainWindow` and `JarvisUI`. It was the application: the HUD, the log, the
settings drawer, the plugin manager, the mute button, the F11 handler, the
confirmation banner's parent, the setup screen's parent.

**Why it went.** No board draws a window. Every remaining surface is a small
always-on-top window of its own, so the window was not merely undrawn — it had
nothing left to hold. `AmbientShell` (`ui/shell.py`) replaces the `JarvisUI`
facade with the same public method names and **no `_win`**, so nothing can
quietly start using a window again.

**The consequence the owner accepted:** Settings and the Plugin Manager have no
UI. There is no screen on which to change them.

**How to reach them now:**

| Was | Now |
|---|---|
| Settings drawer | edit `config/config.json` (the drawer wrote the same keys) |
| Accent colour | `config/config.json` → `ui_accent`, or `ui.theme.apply_ui_accent` |
| Plugin Manager | `plugins/*.json` manifests, plus `config/plugins_state.json` for on/off |
| API key | `config/api_keys.json` |
| Presence mode | the tray panel (board 5) — the segments, or the tray menu's one cycling item |
| Notifications on/off | `config/config.json` → `desktop_notifications` |
| Language | `config/config.json` → `language` |
| Register `jarvis://` links | `python -c "from core import deeplink; deeplink.register()"` — the drawer's Link button is gone; `deeplink.registered()` still reads the OS |
| Microphone / camera / screen | the tray panel's IZIN section (boards 5, 27). Mikrofon is a FACT, not a switch: it is disabled and says so when no device exists. Files and app control are real toggles: they write plugin enablement. |

### The desktop workspace — 11 modules, 3,200 lines

`desktop_workspace.py`, `desktop_layout.py`, `chat_log.py`, `hud_canvas.py`,
`hud_panels.py`, `metric_bar.py`, `metrics.py`, `floating_document.py`,
`floating_documents.py`, `floating_documents_row.py`, `floating_panel.py`,
`floating_row.py`, `floating_window.py`, `drawer_note.py`, `drop_zone.py`.

A tiling desktop inside the window: panels, floating notes, a file drop zone, a
chat log, the metric bar. It needed a full-screen parent to tile in.

**What survives of it.** The face is drawn by `ui/face_canvas.py`, which is the
avatar part of `hud_canvas.py` without the HUD (grid, metric ring, status line,
video frame) — the bubble is 260 px and artboard 4's whole point is that the
status is read from the RING's shape, not from a HUD.

### Editors and viewers — 7 modules, 2,100 lines

`image_editor.py`, `image_canvas.py`, `code_editor.py`, `model_viewer.py`,
`editor_assist.py`, `workspace_browser.py`, `workspace_commands.py`,
`workspace_router.py`.

Text editors, an image canvas, an OBJ viewer, a file browser. All of them were
a pane in the workspace.

**The action that drove them is gone too:** `actions/video_player.py` (941
lines) played audio and video *into* a widget that no longer exists. Its own
module docstring says so: `show_video` / `play_audio` were methods on
`MainWindow`.

### Overlays and panels — 8 modules, 3,500 lines

`overlays.py` (958), `providers_overlay.py` (1,154), `setup_overlay.py`,
`creative.py`, `remote_keys.py`, `wake_sleep.py`, `speech_caption.py`,
`notify_row.py`, `file_access_row.py`, `metric_bar.py`, `camera_preview.py`.

Settings, provider keys, the first-run setup screen, creative tools, the
speech caption, the notification toggle row, the file-access prompt.

**The setup screen is the one to think about.** `main.py` blocks in
`wait_for_api_key()`. The screen that collected the key was inside the window,
so a first run with no key had only one honest answer — and it is now a notice
on the tray plus a line on stdout naming `config/api_keys.json`
(`ui/shell.py::wait_for_api_key`). That is worse than a key field and it is
better than a silent wait; it is written here because it is a real regression
in first-run experience, accepted to get the cut.

### SSH and trading — 5 modules, 1,200 lines

`ssh_manager.py`, `ssh_assist.py`, `trading_terminal.py`, `mt5_trade.py`,
`audio_devices.py`, `audio.py`, `video_controls.py`, `video_fallback.py`.

Tabbed SSH sessions, an MT5 trading terminal, a media bar with device pickers.
The actions behind them (`core/ssh_session.py`, `core/browser_vault.py`,
`core/hand_gesture.py`) still exist and still pass their tests; what is gone is
the only UI that could drive them.

### Gesture layer — 4 modules, 1,000 lines

`hand_gesture.py`, `gesture_os_bridge.py`, `gesture_os_row.py`,
`desktop_ring.py`.

**Artboard 6 is the one board whose surface was not built.** It draws a
listening overlay with a gesture camera tile. The decision module
(`core/gesture_os.py`) is untouched and tested — it is a pure function over a
context — but nothing calls it, because the camera tile is a **proposal**
rather than shipped design (`DESIGN-ambient.md` marks it so). Restoring it means
building the tile first; the bridge and the loop are in git at `376909f1`.

### Assets and helpers — 6 modules, 400 lines

`icons.py`, `browser_icons.py`, `image_tool_icons.py`, `narrative_items.py`,
`narrative_content.py`, `visual_content.py`, `visual_bridge.py`,
`visual_followup.py`, `localization.py`, `file_access_row.py`.

`icons.py` built the tray icon from SVG paths. The tray now draws its icon from
`ui/tray.py`'s own `icon_path()`; the SVG helpers went with the `QIcon`
factory that only the window and the old tray used.

`localization.py` was a second, window-local translator. `core/i18n.py` is the
one that remains, and it is what every surface reads.

---

## Kept, but with nothing to call it

These still exist, still pass their tests, and have **no caller** in this
build. They are listed so nobody mistakes them for live features, and they are
NOT deleted because the day a surface returns they are the expensive half.

| Module | Why it is still here |
|---|---|
| `core/file_access.py` | the permission MODEL is sound; its prompt was `ui/file_access_row.py` |
| `core/gesture_os.py` | the pointer/click/scroll rules; the camera tile is a proposal |
| `core/ssh_session.py` | a working SSH client with no screen to type into |
| `core/pointer_ring.py`, `core/floating.py`, `core/dashboard.py` | the models behind the deleted desktop |
| `core/browser_vault.py` | the encrypted browser-session store; `ui/browser_read.py` asked for consent and is gone |
| `core/risk_policy.py::register` | still has no caller — a known open item, not a new one |

## Deleted with it: 19 test files

`test_window_smoke.py` (1,993 lines), `test_floating.py`,
`test_floating_documents.py`, `test_dashboard.py`, `test_pointer_ring.py`,
`test_file_access.py`, `test_gesture_os.py`'s UI half, `test_audio_bar.py`,
`test_video_wiring.py`, `test_video_audio_tool.py`, `test_ssh_tabs.py`,
`test_trading_terminal.py`, `test_browser_ui_logic.py`, `test_icons.py`,
`test_narrative_content.py`, `test_language_setting.py`,
`test_translation_bindings.py`, `test_ui_setup_wiring.py`,
`test_ui_split_widgets.py`.

**The Qt stub survived.** `tests/test_window_smoke.py` carried 470 lines of
hand-written PyQt6 stand-in that four other test files depended on. It is now
`tests/qtstub.py`, with `install_qt()` / `fresh_ui()` / `restore_ui()`, and it
is why the orb, the face, the bar and the toast queue still run in CI without
PyQt6 installed.

---

## How to bring something back

1. **Look at the board first.** If a surface is not on one of the twelve, it is
   a `DESIGN-ambient.md` proposal and needs the owner's decision, not a commit.
2. `git checkout 376909f1 -- ui/<file>.py` — one file, not the tree.
3. Re-point its imports: `ui/window` is gone, `ui/icons` is gone.
4. If it touched `MainWindow`, it needs a holder. `AmbientShell` deliberately
   has none; a surface that needs a parent needs a different design.
5. Add it to `tests/test_ui_split.py::test_the_package_has_exactly_the_mockup_modules`
   — that test is the list, and it fails on an unannounced module.
6. Add the row back above, with a line saying which board justifies it.

## Known gaps, stated plainly

- **No Settings, no Plugin Manager.** Accepted, listed above with the file to edit.
- **No first-run key entry.** A notice, and `config/api_keys.json`.
- **No camera/gesture overlay.** Artboard 6 is a proposal; the decision module waits.
- **No media playback.** `actions/video_player.py` went with the widget.
- **Untested on Windows.** Frameless transparency, click-through
  (`WindowTransparentForInput`), focus return after Esc and DPAPI can only be
  proven on a real Windows desktop. CI runs Linux.
