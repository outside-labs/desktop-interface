# Desktop Interface

Typed native desktop APIs for Python, starting with macOS. The library is being
built around documented system APIs and `ctypes`, with no third-party runtime
dependencies in the core.

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
attributes/actions and optional confirmation. Keyboard/mouse input, accessibility
inspection, and capture remain planned.
Importing the package does not load native libraries or request system access.

Python 3.12 or later is required. Development uses Python 3.14; CI checks Python
3.12 and 3.14 on Linux, and Python 3.14 on Windows and macOS. These checks cover
the portable foundation and do not imply a working native backend on each OS.

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

Setters check writability; focus checks the app's focused-window/frontmost
attributes and the window's advertised raise action before changing anything.
An application may reject or adjust a request. Without `timeout`, return `None`
means submission only. `timeout=0..30` waits for a copied `WindowState` or raises
`OperationTimeoutError`; a timeout does not roll back a delivered action.
Matching has a five-second query budget, at most 128 Accessibility windows and
0.25-second individual IPC timeouts. Confirmation has a separate wait budget
with a bounded final read. No global Accessibility timeout is changed.

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
```

The distribution check builds wheel and source archives, rebuilds the source
archive, and checks both installations in fresh environments outside the
checkout. Tests use the standard library. Routine checks do not send input,
inspect application contents, or capture the screen.

The [issue queue](https://github.com/outside-labs/desktop-interface/issues) and
[development Project](https://github.com/orgs/outside-labs/projects/10) track
scope, dependencies, and acceptance criteria. The first delivery batch covers
packaging, core contracts, and the private native binding layer.

Version 0.1.0 is an unpublished development version. The repository starts
private; a license and publication path have not been selected.
