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
| 1 | Orb overlay — Siaga & area klik | a ring in a 146 px box on the desktop; only the ring takes clicks | `ui/orb_overlay.py`, `ui/orb_place.py`, `ui/orb_canvas.py` |
| 2 | Toast — antrean & batas harian | three cards at 340 px, the fourth replaces the oldest and is counted; 8 s; never takes focus | `ui/toast_queue.py`, `ui/toast_card.py`, `ui/toast_stack.py` |
| 3 | Command bar — Ctrl+Space | one line, Esc gives focus back | `ui/command_bar.py` |
| 4 | Orb overlay — interaksi & status | left click opens the panel, right click a short menu, a drag snaps to an edge; four states read from the orb itself | `ui/orb_paint.py`, `ui/ambient_shell.py`, `ui/orb_snap.py` |
| 5 | Panel baki sistem | the 460×660 tray panel: three segments, four quick actions with chords, today's suggestion, permissions, one line to type in | `ui/tray_panel.py`, `ui/tray_pages.py`, `ui/tray_panel_model.py` |
| 6 | Overlay suara + kamera gestur | listening overlay, gesture camera tile | **proposal — see below** |
| 23 | Fokus — toast ditahan | held notifications counted by `core/presence_mode`; a strip that states no deadline; three quick rows of its own (no "Ubah durasi"); a persisted scheduling pause; the second quota sentence, counted | `ui/toast_queue.py`, `ui/toast_stack.py`, `ui/tray_paint.py`, `ui/tray_panel_model.py`, `actions/proactive.py`, `ui/tray_panel_wiring.py` |
| 24 | Senyap — orb memudar | the orb shrinks to 18 px, loses its glow, goes dotted, and writes its mode under the ring; the 146 px frame does not resize | `ui/orb_paint.py`, `ui/orb_canvas.py`, `ui/orb_place.py` |
| 25 | Risiko: konfirmasi | BERISIKO heading, "Tindakan ini tidak bisa diurungkan.", ASAL PERMINTAAN fed by the real entry point (voice/typed/unknown), Konfirmasi/Batal, Enter confirms and Esc cancels with the initial focus still on Batal; the store lives in `core/input_source` so the audio callback never imports Qt | `ui/confirm_banner.py`, `core/input_source.py`, `ui/shell.py` |
| 26 | Riwayat tugas + Urungkan | task history with undo, audit tail, export and clear | `ui/tray_panel.py` (history page) |
| 27 | Izin & Privasi | three indicators with cards, four explicit permissions with cards, a per-page title, erase — and **no guest mode** (see below) | `ui/tray_pages.py`, `ui/tray_panel_model.py` |
| 28 | Tema terang — panel baki | the same panel in light colours, plus the switch that reaches it | `ui/tray_pages.py` (`PALETTES["light"]`), `ui/tray_theme.py` |

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
| **Mode tamu** | **Deleted from the panel, the wiring and both catalogues.** Guest mode needs every surface to stop reading memory and history, and nothing does that. The switch used to be drawn and to answer a click with a sentence; a disabled switch was rejected too, because it still promises the feature exists. The owner's ruling: if it cannot be done, do not draw it — see `docs/mockups/DESIGN-ambient.md`, board 27. |
| **Dikte** | Works, but it is a SIX-SECOND hold released on a timer — a button cannot express "until I let go". The press-and-hold version is the chord on the same row. |
| **Cari berkas** | Opens the command bar with `Cari berkas ` already typed instead of searching: the search needs a query, and the bar is where the user already types one. |

The chords printed on the rows (`Ctrl+Shift+S`, `Ctrl+Win`, `Ctrl+Shift+F`,
`Ctrl+Shift+J`) are the ARTBOARD'S. Only `Ctrl+Shift+J` (summon) and `Ctrl+Space`
(command bar) are actually bound by this program; the other three are printed
labels, not registered hotkeys. A chord on a row is not a promise the OS owns it.

**The theme switch** is a 28 px control in the header, marked `A` / `D` / `L`.
It cycles the SETTING (`auto → dark → light → auto`) and the value is written to
`config/api_keys.json` as `ui_theme`. The button shows the setting, not the
palette it resolved to — a button reading "light" because `auto` resolved light
could never be set back to auto.

`auto` is read from `ui_os_theme` in the same file, **not** from a live desktop
query: detecting the running theme is a `QGuiApplication.styleHints()` question
and belongs to whoever owns the QApplication. On a machine where the key is
absent — every Linux desktop, and Windows until something writes it — `auto` is
dark. That is a limitation, not a claim: the light palette is reachable, the
switch to reach it exists, and following the OS automatically is the part still
missing.

The suggestion row is empty in this build and says "Belum ada saran hari ini."
`core.suggestion_quota` counts suggestions; nothing generates them yet.

### The risk gate: what a confirmation still costs

Board 25 draws the confirmation. What it does not draw is HOW OFTEN it appears,
and that number was wrong in a way no screenshot could show: `core/tool_risk`
classifies sixteen tools in `actions/`, four of them had per-action tables and
seven were in no table at all. An unlisted tool used to be refused as `risky`
for a reason that had nothing to do with danger — `open_app` asked the user to
confirm opening Spotify, and `desktop_control(action="list")` asked before
reading a wallpaper filename. A banner nobody needs is a banner nobody reads,
and the one in front of a bank transfer is the one that gets dismissed with it.

Fixed: those four tools now have sub-action tables, so reading is `safe` and
bulk file operations are `risky` for a stated reason. `core.risk_policy` is
also told what was discovered at startup (`tool_risk.register_discovered`),
which is the caller `register()` never had.

**The four that were escalated now have an undo, and it is a real one.**
`open_app`, `reminder`, `youtube_video(action="play")`,
`browser_control(action="go_to"|"new_tab")` each push a closure onto
`core/undo` at the moment the change is made, so the gate can call them
`medium` without the promise being empty. The gate still escalates any `medium`
whose closure is missing — that rule did not move.

What each undo actually does, and what it refuses to claim:

| action | closure | the honest answer when there is nothing to reverse |
|---|---|---|
| `open_app` | closes the process `wait_for_launch` **saw appear**, through the same `appidentity.request_close` the close guard uses | "already closed — nothing to undo" |
| `reminder` | `schtasks /Delete`, `launchctl unload`, `systemctl --user stop`, or `atrm <n>` — whichever scheduler created it — then deletes the notify script | "the reminder for HH:MM has already fired" |
| `youtube_video:play` | a browser back (`alt+←`, `cmd+←` on macOS) in the user's own browser | names the missing `pyautogui` instead of pretending |
| `browser_control` | asks the internal browser to go back and repeats its answer | "no page to go back to" |

Three of these are deliberately **not** "close the tab". A tab this process did
not create is somebody else's window, and closing it is a larger change than the
one being reversed. Going back is the reversal the user would perform, which is
the only definition of undo this project accepts.

Two things it still cannot do, said here rather than discovered: raising an
already-running app registers **no** undo (it only changed the z-order, which
the assistant cannot observe to restore), and `browser_control` can only walk
back as far as the browser's own history — it cannot un-read a page.

`flight_finder` stays in the register for the opposite reason: it reads a public
page and changes nothing, so calling it "undoable" would be inventing a meaning
for the word. `tests/test_tool_risk.py` keeps the one-row register;
`tests/test_action_undo.py` proves each closure above.

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

**The setup screen was the one to think about, and it is back.** `main.py`
blocks in `wait_for_api_key()`. The screen that collected the key was inside
the window, so after the cut a first run with no key had only one honest answer
— a notice on the tray plus a line naming `config/api_keys.json`. That was a
real regression in first-run experience, accepted to get the cut, and recorded
here as one.

It is no longer a regression. **No artboard draws it**, so it borrows the
language it must not contradict: the 460×660 panel, board 5's dark palette, and
`panel_head()`'s "JARVIS / subtitle" header from `build.py`. What it adds is the
one control the mockup has no place for — a password field for the API key, one
button, three sentences (works / rejected / saved-but-unverified).

`ui/setup_window.py` draws and decides; `ui/setup_screen.py` is the thread hop
(`main.py`'s runner thread and the asyncio recovery loop both ask for it, and Qt
may only build widgets on the Qt thread). The decisions behind it are the
owner's, taken on 2026-11-22:

| Question | Decision |
|---|---|
| Where is the key stored? | `config/api_keys.json` only. The OS keychain write was removed. |
| Can it be skipped? | No. There is no "Lewati" button, not even a disabled one. |
| Is the key tested? | Yes — `core/key_check.py` makes one real `models.get` call. |
| And offline? | The key is saved with a sentence saying it was not verified. |

`tests/test_setup_window.py` (22 tests) and `tests/test_shell_setup.py` (11)
cover the three verdicts, the no-skip rule, and both wait loops exiting.

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
| `core/gesture_os.py` | **no longer orphaned** — `core/gesture_bridge.py` calls it per frame (see board 6); the rules are live, the camera is Windows-only |
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

## Board 6: the voice overlay, and the three promises a screenshot cannot keep

The artboard draws a 1280×720 frame: a 2 px cyan edge, a radial glow, a 300×200
camera tile holding a pinching hand, the orb at 44 px, the transcript and its
answer, and a footnote. The drawing is the easy half. The footnote is the spec,
and it makes three claims — so each one is a function that returns a number:

| footnote clause | where it lives | what the test asserts |
|---|---|---|
| "Glow tepi hanya saat overlay aktif" | `voice_overlay.edge_alpha(active, state)` | returns **exactly 0.0** when inactive, for every state; speaking is brighter than listening |
| "Esc keluar" | `VoiceOverlay.handle_escape()` | closes an active overlay and calls `on_close`; returns False on a hidden one, so Esc still belongs to whatever the user is looking at |
| "Ctrl+Alt+G menjeda gestur" | `VoiceOverlay.handle_toggle_gestures()` | pauses gestures, **keeps** the overlay and the transcript, and clears the frozen hand |

Two decisions in that table are the design, not the implementation:

* **Pausing gestures is not closing the overlay.** The user stopped waving, not
  talking. Taking the transcript away because the hand is idle would answer a
  question nobody asked, and the transcript is the reason the overlay is up.
* **Esc on a hidden overlay is not consumed.** A window that swallowed Esc while
  invisible would break whatever the user was actually doing.

**What is deliberately NOT implemented, because it cannot be shown here:**
click-through. The footnote promises Esc closes the overlay, and
`WindowTransparentForInput` would make the window unable to receive the key that
fulfils that promise. `test_the_window_flags_are_the_three_that_matter_and_not_click_through`
pins the absence. Windows click-through and focus return after Esc stay in the
"untested on Windows" list below rather than being assumed.

**The two lines of text are fed from `write_log`, not from new call sites.**
Every sentence the user says and every sentence the assistant answers already
reaches `AmbientShell.write_log` with a `You: ` or `<name>: ` prefix, so
`voice_wiring.show_exchange` splits those two prefixes there. A second call site
in `main.py` would be a second thing to keep in step, and the one that drifted
would be the one on the full-screen surface. The program's own lines — `SYS:`,
`ERR:`, `USR:`, `TOOL:` — are dropped: putting them on the transcript line would
make the overlay claim the user said "Push-to-talk unavailable". Anything that is
neither the user's nor a machine prefix is the assistant's own speech, which is
the same rule `write_log` already uses to decide what to notify about.

**When it is on screen is a rule, not a side effect.** `ui/voice_wiring.py`
holds it in one pure function: the overlay covers the desktop for
`LISTENING` and `SPEAKING` and for nothing else. `THINKING` is deliberately
absent — the question is in, the answer is not out, and a full-screen frame that
appeared between the two reads as a hang. `NO MIC` is absent for the opposite
reason: a 1280×720 frame announcing that it is listening, on a machine with no
microphone, is the worst possible moment for one. The window is built during
start-up and shown on the first LISTENING, so its construction cost is not paid
at the moment the feature is judged.

Esc goes through `voice_wiring._on_close` → `shell.request_sleep()`, the same
path the tray's Sleep control uses. "Esc keluar" has to mean the microphone
closed, not only the picture — the close handler is tested for exactly that.

**Ctrl+Alt+G is now a chord the program can actually bind.** The footnote
prints it, and until this point nothing listened for it: `core/hotkey`'s three
key-code tables carried `ctrl`, `shift`, `alt`, `space`, `f8`–`f10`, CapsLock and
Insert, and no `g`. A letter missing from one of those tables binds on Windows
and falls back to a window-scoped hook elsewhere — silently, and only for some
users — so `g` was added to all four (VK, X11 keysym, macOS kVK, Qt name) and a
test pins it in each.

The binding does **not** stop the pointer itself. `core.hand_gesture` polls the
same chord as its own emergency stop, precisely so that stop does not depend on
this program's event loop. What the binding adds is the half a controller cannot
know: telling the overlay to show "GESTUR DIPENGGU", and sending no further
samples while it is up. A machine where the chord cannot bind globally still has
the kill switch; it only loses the word on the tile.

**The hand now reaches the desktop — and the switch that allows it is off
until somebody turns it on.** `core/gesture_os.py` decided what a hand may do
and `core/gesture_os_pointer.py` knew how to deliver it, and neither had a
caller outside its own tests: the tile showed the hand and the hand controlled
nothing. `core/gesture_bridge.py` is the missing third piece and nothing more —
samples in, one policy call out to the desktop.

| rule | how it is kept |
|---|---|
| **off means off** | `gesture_os_enabled` in the config is `False` by default, and the disabled path builds no pointer, imports no driver, and holds no reference. A corrupt config reads as *off*, never *on* |
| **switching off lets go** | `disable()` asks the policy for `release_now()` and delivers it there and then — there may be no next frame, and a button left down makes the desktop drag-select and cannot be fixed by waving |
| **our own focus freezes the hand** | `gesture_context()` reads it from Qt; with no window there is nothing of ours to have focus |
| **a confirmation freezes the hand** | `core.confirm.pending_title()` — the same function that already expires banners. Unreadable is treated as *a banner might be up*, because freezing a hand for a frame costs nothing and a webcam click on a transfer confirmation costs everything |
| **a lost hand releases the button** | on that same frame, which is rule 3 of the policy, driven from the seam |
| **nothing raises into the Qt thread** | every path is on a 12 fps timer; a driver failure is counted and the loop continues, because the gesture that releases a stuck button has to arrive after one that failed |

Where it runs: `ui/hand_feed.HandFeed` owns the bridge and pumps it from the
same sample the tile draws, on the same timer, in the same Qt thread. The
camera worker never calls pyautogui — it publishes, and this polls.

**What it cannot do here, stated in the module that cannot do it:** this runner
has no pyautogui, no camera and no display, so the delivery path is exercised
with a recording mouse and the policy with the real `HandPointer`. Nothing
above claims a real cursor was moved. On Windows the pipeline is bounded by the
same three calls the allowlist names — `moveTo`, `mouseDown`, `mouseUp`,
`scroll` — and a test fails if a fifth appears.

**Still missing, and named rather than hidden:** there is no control in the
panel for this switch, because board 27 draws exactly four permissions and a
fifth would be a change to the artboard, not to the code. The setter is
`ui.hand_feed.set_gesture_os(shell, on)`; until a surface offers it the feature
is reachable only by editing `config/api_keys.json`. That is a gap with a
proposed fix, not a finished feature.

**The hand on the tile comes from the camera that already drives the OS
pointer.** `ui/voice_wiring.HandFeed` owns one `WorkspaceHandController`, polls
it on the overlay's own 12 fps timer, and puts the **first** hand of the newest
frame on the tile. An empty sample — a lost hand, a stale frame, or a closed hand
that has not been deliberately re-opened — empties the tile rather than freezing
the last picture, which is the same signal `core.gesture_os` uses to release a
held button. The tile is lit for `status == "active"` and for nothing else:
`starting`, `off`, `windows_only` and `error` all mean the hand is not backed by
frames. Ctrl+Alt+G sends nothing at all, so the pause is visible in the one
place a user can see it. The feed is stopped **before** the event loop quits —
a camera light still on after Quit is the one failure nobody forgives.

Off Windows the feed refuses (`WorkspaceHandController.start()` sets
`windows_only`, and mediapipe is a Windows-only dependency here), the tile reads
"KAMERA NONAKTIF", and that is the honest state rather than a placeholder.

**The split is three files, and the ceiling is why.** The first draft —
window, state, hand geometry and every Qt call — was 790 lines against a 600
line ceiling. `ui/voice_hand.py` took the geometry (the only part that comes
from outside the program), `ui/voice_paint.py` took the Qt calls, and
`ui/voice_overlay.py` kept the rules. A fourth, `ui/voice_wiring.py`, is what
knows about the shell; the surface must not depend on it. `test_the_painter_never_decides_anything`
holds the seam: the painter may CALL `status_word`, never DEFINE it.

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
- **The camera/gesture overlay exists but cannot open a camera here.** Board 6
  is built (`ui/voice_overlay.py`, `ui/voice_hand.py`, `ui/voice_paint.py`); the
  tile it draws is fed by `core.workspace_gesture`, whose camera needs
  mediapipe, which this repo's `requirements.txt` installs on Windows only. On
  Linux the tile reads "KAMERA NONAKTIF" — the honest state, not a placeholder.
- **No media playback.** `actions/video_player.py` went with the widget.
- **Untested on Windows.** Frameless transparency, click-through
  (`WindowTransparentForInput`), focus return after Esc and DPAPI can only be
  proven on a real Windows desktop. CI runs Linux.

## The camera watcher, and why it has no switch on screen

`core/security_camera.py` and `plugins/security_camera.py` shipped from a branch
cut before the controls drawer was removed. That branch drew a **SECURITY
CAMERA** row in the drawer, next to **FULL FILE ACCESS**; the drawer is not in
any mockup, so it is gone, and the row went with it.

The watcher itself is unchanged and still obeys its three rules — off by
default, the camera is never opened while off, it never speaks first, nothing is
recorded or uploaded. What changed is only how a person reaches it: the
`security_camera.enabled` key in `config/api_keys.json`, and nothing else.

- **A fifth row was not added to board 27.** It would be a control the artboard
  does not draw — the same reason the drawer was deleted — and two rows is how
  the permissions page stops being the four things the mockup shows. Between a
  setting that lives in a config file and a surface that contradicts the
  mockup, the config file wins.
- **`tests/test_security_camera.py` was rewritten where it touched the row.**
  Forcing the switch on and off now goes through the same config file a person
  would edit, so the test still fails if the watcher becomes unreachable — it
  just no longer fails because a drawer is missing.
- **The plugin declares `level: safe`.** It reads an in-memory record, takes no
  picture, and cannot enable the watcher; the manifest says so.

### `core/file_access.py` was exempt from the coverage map for the wrong reason

It was listed as "its prompt was a widget; there is no window to ask with".
The PROMPT was a widget. The module is a policy plus a path check, it is still
consulted by `actions/file_controller.py` on every file operation, and it never
needed a window — so the exemption described a caller that had died, not a
module that could not run. It now has `tests/test_file_access.py`, and writing
that test found a real bug:

- **Turning the feature ON took the home folder away.** `effective_roots()`
  returned only the granted roots on the ON branch, so granting one extra folder
  silently revoked access to everything the assistant could already reach.
  `describe()` had been telling the user the opposite all along ("nothing
  *outside* your home folder is reachable"), which is how the disagreement was
  caught: the sentence and the check could not both be true. Home is now always
  one of the effective roots.

## The hang: an icon that answered nothing

On Windows the tray icon appeared and then responded to no click at all. That
combination is the signature of a blocked Qt thread rather than a failed start:
`QSystemTrayIcon.show()` paints the icon synchronously, so an icon exists even
when `app.exec()` is never reached — or when the loop behind it never runs.

Four defects produced it, and each one is the same shape: work that looks
harmless in a file and is a machine-gun on the one thread that can draw.

- **The face bubble repainted 893 polygons 30 times a second.**
  `ui/face_canvas.py` ran one 33 ms timer, and every tick called `update()`.
  Every repaint walked the visible half of a 1,554-facet head: 893
  `drawPolygon` calls plus their `QPolygonF`, three `QPointF` each, and a
  `QLinearGradient` with two or three `setColorAt` calls. Measured on this
  mesh that is **26,790 polygons and over 100,000 Qt calls per second**, all on
  the Qt thread. The event loop then serviced the tray only in the gaps.
  Two changes: the repaint is now a separate decision from the step
  (`should_repaint`, `IDLE_REPAINT_MS` = 200 ms for a still face, every step
  while speaking), and the idle FILL draws every third visible facet
  (`IDLE_FACET_STRIDE`). The wireframe and the facial features are untouched,
  so the silhouette, the eyes and the mouth stay exact.
- **`start_voice_overlay` ran outside any `try`.** It builds a 1280×720
  window, starts a camera worker and binds a chord — and it is called from
  `start_interface`, which runs on the Qt thread before `exec()`. One exception
  there left the tray icon on the taskbar with no event loop behind it.
- **`start_summon_hotkey` ran outside any `try`** for the same reason, and it
  probes the OS (`GetAsyncKeyState` on Windows, `XOpenDisplay` on X11).
- **The guard is now asserted by name.** `tests/test_face_frame_budget.py`
  walks `start_interface` and fails on any `start_*` call that is not inside a
  `try`, so the next surface added to that function cannot reopen the hole.

`HoloAvatar.paint` gained `facet_stride`, and `ui/face_canvas.py` gained
`should_repaint` — a pure function rather than an inline `if`, because the
first version of the test read the source text and a mutation that replaced the
condition with `if True:` passed it.

**Not proven here.** This was diagnosed by reading, measuring the mesh and
driving the callbacks with a stub; Qt cannot run in this sandbox (the wheel
installs, the system libraries do not). Whether the Windows tray now answers
clicks is a check on the real desktop, and it is in `docs/verification.md`.
