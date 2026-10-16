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
Display discovery, window control, keyboard and mouse input, accessibility inspection, and screen
capture are planned features. There are no desktop automation operations yet.
Importing the package does not load native libraries or request system access.

Python 3.12 or later is required. Development uses Python 3.14; CI checks Python
3.12 and 3.14 on Linux, and Python 3.14 on Windows and macOS. These checks cover
the portable foundation and do not imply a working native backend on each OS.

## Development

```sh
uv sync --locked
uv run --frozen python -m unittest discover -s tests -v
uv run --frozen python scripts/check_distribution.py
# On macOS with the system SDK available:
uv run --frozen python scripts/check_macos_abi.py
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
