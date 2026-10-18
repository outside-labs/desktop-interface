# Changelog

## 0.1.0 — 2026-10-18

Initial alpha release with Python 3.12+ support and no runtime dependencies.

- Immutable geometry, backend-qualified identifiers, capability reports and
  consistent errors, with passive imports on macOS, Windows and Linux.
- Explicit macOS sessions and permission checks/requests.
- Active-display snapshots and logical/pixel coordinate conversion.
- Filtered window discovery, owner-aware references and bounded window control
  through Accessibility, including optional confirmation.
- Physical keys, Unicode text, shortcuts and scoped key ownership.
- Logical mouse motion, buttons, scrolling, dragging, cancellation and scoped
  button ownership.
- MIT licensing and typed wheel/source distributions.

Native operations currently require macOS. Live verification covers macOS
27.0.1 arm64, Python 3.14.7, one display and a synthetic AppKit fixture. Other
platform/architecture combinations and applications require separate native
verification. Accessibility-tree inspection, global listeners, hotkeys and
screen capture are planned. APIs may change before 1.0.
