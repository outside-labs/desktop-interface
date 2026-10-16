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
backing-pixel dimensions, rotation and main/mirror metadata. Window control,
keyboard/mouse input, accessibility inspection, and capture remain planned.
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
from desktop_interface import Desktop, Point

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
