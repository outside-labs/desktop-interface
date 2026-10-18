# Desktop Interface

Typed native desktop APIs for Python, starting with macOS. The library uses
documented system APIs and `ctypes`, with no third-party runtime dependencies
in the core.

The current foundation provides immutable geometry, backend-qualified display
and window IDs, conservative capability reports, and consistent error types.
The private native layer provides explicit function signatures, lazy system
library loading, and deterministic reference cleanup. Its macOS ABI declarations
are checked against system SDK headers, with a synthetic CoreFoundation string
used to verify Unicode and ownership without accessing the desktop.
An explicit macOS `Desktop` session provides nonprompting permission checks and
separate permission requests. Active-display snapshots provide logical bounds,
backing-pixel dimensions, rotation and main/mirror metadata. Window discovery
provides copied metadata, exact filters and references that revalidate their
native ID and owner. Accessibility-backed window control supports advertised
attributes/actions and optional confirmation. Keyboard input supports physical
positions, Unicode text and owned key contexts. Mouse input supports logical
pointer motion, buttons, scrolling and cancellable dragging. Accessibility-tree
inspection, listeners and capture remain planned.
Importing the package does not load native libraries or request system access.

## Installation and support

```sh
python -m pip install desktop-interface==0.1.0
```

Python 3.12 or later is required. The native backend currently requires macOS.
Windows and Linux can import the package and use portable value types; creating
a `Desktop` session on those platforms raises `UnsupportedPlatformError`.

| Area | Version 0.1.0 |
| --- | --- |
| Portable foundation | Immutable geometry, qualified IDs, capability reports, errors and passive imports. |
| Permissions | Explicit macOS checks and requests; construction does not prompt. |
| Displays | Active-display metadata, immutable topology and logical/pixel coordinate conversion. |
| Windows | Filtered discovery, owner-aware references and bounded Accessibility-backed control. |
| Keyboard | Physical key positions, Unicode text, shortcuts and scoped held keys. |
| Mouse | Logical motion, buttons, scrolling, dragging and scoped held buttons. |
| Planned APIs | Accessibility-tree inspection, global listeners, hotkeys and screen capture. |

CI checks Python 3.12 and 3.14 on Linux, and Python 3.14 on Windows and macOS.
These checks cover portable contracts, synthetic native values and installed
distributions. Live native conformance has been verified on macOS 27.0.1 arm64
with Python 3.14.7, one active display and a synthetic AppKit fixture. That
fixture acknowledged window control, Unicode and physical-key delivery, mouse
clicks, dragging and scrolling; its window state and cursor were restored.
Older macOS, Intel, multiple/rotated displays, other applications and non-US
keyboard-layout output remain unverified.

This is an initial alpha release. Public APIs may change before 1.0; changes
and compatibility notes are recorded in
[the changelog](https://github.com/outside-labs/desktop-interface/blob/main/CHANGELOG.md).

## Permissions

```python
from desktop_interface import Desktop, Permission

with Desktop() as desktop:
    status = desktop.permissions.check(Permission.ACCESSIBILITY)
    print(status.state)
```

Construction is passive. `check()` and `check_all()` inspect existing grants
without submitting requests. `request(permission)` is an explicit main-thread
operation that may show system UI. Its `request_sent` flag records submission,
not proof that a prompt appeared or consent was granted. Recheck after the user
changes System Settings. macOS false preflights report `UNKNOWN`: those APIs
cannot reliably distinguish a denied grant from one never requested. A restart
requirement also stays unknown when the OS does not expose it.

Permission grants do not imply that a desktop feature is implemented. Consult
`desktop.capabilities()` for feature support. Close sessions explicitly or use
their context manager; retained managers reject operations after session close.

## Display snapshots

```python
from desktop_interface import Desktop

with Desktop() as desktop:
    topology = desktop.displays.snapshot()
    if topology.main is not None:
        location = topology.logical_to_pixel(topology.main.bounds.origin,
                                             display_id=topology.main.id)
        assert topology.pixel_to_logical(location) == topology.main.bounds.origin
```

Snapshots list active drawable displays. Sleeping outputs and online-only
hardware mirrors are outside that list. Metadata is read twice with a bounded
retry when IDs or modes change; the result is a stable observation, not an
atomic operating-system transaction.

Bounds use global logical points, including negative monitor origins. Pixel
dimensions come from the current display mode and use desktop orientation;
they do not claim to describe panel hardware. `PixelPoint` is a continuous
display-local coordinate without implicit raster rounding. Rotation is already
normalized when mapping mode dimensions; conversion does not rotate again.
Overlapping displays require an explicit display ID. A converted pixel location
belongs to its exact topology snapshot and cannot be silently reused with a
different snapshot. Old snapshots remain useful as immutable data after close.

## Windows

```python
from desktop_interface import Desktop

with Desktop() as desktop:
    for record in desktop.windows.list():
        print(record.id, record.process_id, record.bounds)
```

`list(process_id=..., onscreen_only=True)` copies matching metadata. The process
filter is applied before decoding title or owner text. Missing/redacted names,
bounds and owner identity remain `None`; they do not imply a permission verdict.
The macOS on-screen flag follows its native contract: an absent flag means false.

`get(window_id)` creates a reference to an explicit ID. `find(process_id=...,
title=..., owner_name=...)` uses exact, case-sensitive matching and requires a
unique result. No match raises `TargetNotFoundError`; multiple matches raise
`AmbiguousTargetError`. A missing owner can be listed but cannot be bound to a
reference whose identity could not be verified.

`window.read()` queries that specific window again and rejects disappearance
or a changed owner with `StaleTargetError`. Its `initial` metadata remains an
immutable snapshot. Native IDs and PIDs can both be recycled, so this pair is
not a durable identity across process/session restarts. All live references
reject reads after their owning desktop session closes.

Each metadata read is bounded to 4096 records and each text field to 32768
UTF-16 units / 65536 UTF-8 bytes. Malformed or excessive native metadata fails
explicitly instead of returning a silently truncated list. A Quartz API null
result is a native failure, distinct from a valid empty list; a GUI session
or window server may be unavailable. No permission request is triggered.

`window.state()`, `move(Point(...))`, `resize(Size(...))`, `focus()` and
`minimize(True/False)` require an existing Accessibility grant. The public
Accessibility API has no documented Quartz-window-ID lookup: control requires
a unique match by owner PID, bounds (within half a logical point), and title
when available. Unavailable or indistinguishable matches fail before writing.
IDs/PIDs and metadata checks cannot eliminate all target-replacement races.

Setters check writability; focus checks the window's main attribute, the app's
frontmost attribute and the advertised raise action before changing anything.
An application may reject or adjust a request. Without `timeout`, return `None`
means submission only. `timeout=0..30` waits for a copied `WindowState` or raises
`OperationTimeoutError`; a timeout does not roll back a delivered action.
Confirmed move/resize waits for Quartz and Accessibility geometry to agree,
so a following operation can rematch the updated window.
Matching has a five-second query budget, at most 128 Accessibility windows and
0.25-second individual IPC timeouts. Confirmation has a separate wait budget
with a bounded final read. No global Accessibility timeout is changed.

## Keyboard input

`desktop.keyboard.press(Key.A)`, `shortcut(Key.COMMAND, Key.A)` and
`with desktop.keyboard.hold(Key.SHIFT): ...` use physical positions named after
a US reference keyboard. The active layout determines their text; there is no
implicit character-to-key lookup. Caps Lock, Fn, media and device-specific keys
are outside this initial key set. `is_pressed()` reports the current Quartz
state, separate from an event listener.

`type_text("Fixture 👋")` supplies Unicode independently of key-position mapping.
It validates the full string, preserves non-BMP surrogate pairs, and limits a
call to 16384 UTF-16 units. Unpaired surrogates fail before posting. Each Unicode
scalar gets a prepared down/up pair; frameworks can still reinterpret or ignore
the Unicode payload. Existing modifiers are preserved and can affect delivery.

Posting requires an existing event-posting grant and targets the current global
input stream. A successful return means submission, not acknowledgement by an
application. Use an explicit fixture or verify your target's focus. No permission
dialog is triggered by a keyboard method.

`down()` returns whether it acquired a key; `up()` releases only a key acquired
by this session. Keys already down and nested holds are preserved. Contexts,
exceptions, cancellation and session close release acquisitions in reverse
order. Cleanup attempts every release and groups failures; OS rejection or
revoked access can prevent actual release. Concurrent physical input cannot be
distinguished perfectly from synthetic ownership. A closed session rejects input.
Durations and total text-interval waits are bounded to 30 seconds. Pass a
`threading.Event` as `cancel` for interruptible waits and text sequences.

## Mouse input

`desktop.mouse.position()` returns a global logical `Point`.
`move(Point(...), duration=...)`, `click()`, `drag(Point(...))`, `down()`, `up()`
and `with desktop.mouse.hold(MouseButton.LEFT): ...` submit pointer/button
events. Left, right and middle buttons are supported; multiple held-button
chords are explicitly unsupported. Nested holds preserve existing acquisitions,
and a click does not release an externally held button. Dragging refuses to
acquire an externally held button. Session close releases both buttons and keys.

Motion checks active-display bounds, including negative origins, without pixel
scaling. Timed motion uses up to 60 steps per nominal second, plus native-call
overhead. The full path must remain on active displays; a straight path through
a monitor gap is rejected before pressing a drag button. Topology changes
between steps abort the path and release acquired state. There is no atomic
guarantee against a topology or focus change between validation and OS delivery.
Use a `threading.Event` as `cancel` for motion, dragging or repeated clicks.

`scroll(vertical, horizontal=0, unit=ScrollUnit.LINE)` accepts signed 32-bit
deltas. `ScrollUnit.PIXEL` selects Quartz pixel-scroll units; those deltas are
independent of display-coordinate conversion. Positive native deltas conventionally
scroll up/left; applications and system scrolling preferences determine the
effect. Large deltas may behave differently by application. `click(count=2)`
sets native click-count fields; no system double-click timing is changed.
Pointer writes require the same event-posting grant as keyboard input. Reads
and successful posting do not establish that a particular application received
or acted on an event.

## Development

```sh
uv sync --locked
uv run --frozen python -m unittest discover -s tests -v
uv run --frozen python scripts/check_distribution.py
# On macOS with the system SDK available:
uv run --frozen python scripts/check_macos_abi.py
# Opt-in, nonprompting native grant check; never run by default CI:
uv run --frozen python scripts/check_native_desktop.py --permissions
uv run --frozen python scripts/check_native_desktop.py --displays
# In a logged-in GUI session, for an explicitly selected synthetic fixture:
# uv run --frozen python scripts/check_native_desktop.py --window-id ID --process-id PID
# From a logged-in GUI Terminal; opens and closes a synthetic fixture window:
uv run --frozen python scripts/check_live_desktop.py
# Explicitly exercise/restore only that fixture's window attributes:
uv run --frozen python scripts/check_live_desktop.py --window-control
# Also submit known text and a physical key; temporarily leave the fixture focused:
uv run --frozen python scripts/check_live_desktop.py --keyboard
# Exercise all three control surfaces against the fixture and restore its state:
uv run --frozen python scripts/check_live_desktop.py --window-control --keyboard --mouse
```

The distribution check builds wheel and source archives, rebuilds the source
archive, and checks both installations in fresh environments outside the
checkout. Tests use the standard library. Routine checks do not send input,
inspect application contents, or capture the screen.

## Releases

After the release commit passes CI on `main`, a matching version tag (for
example, `v0.1.0`) starts
[the release workflow](https://github.com/outside-labs/desktop-interface/blob/main/.github/workflows/release.yaml).
It reruns the cross-platform checks, verifies tag and package versions, and
checks both distributions and clean installations before retaining the exact
artifacts for publication. A separate job publishes through PyPI Trusted
Publishing in the `pypi` environment, without a stored API token. The trusted
publisher must name `outside-labs/desktop-interface`, `release.yaml` and `pypi`.
Allow the intended version tag in the environment's deployment policy before
pushing it.

The [issue queue](https://github.com/outside-labs/desktop-interface/issues) and
[development Project](https://github.com/orgs/outside-labs/projects/10) track
scope, dependencies, and acceptance criteria.

## License

Desktop Interface is available under the
[MIT License](https://github.com/outside-labs/desktop-interface/blob/main/LICENSE).
