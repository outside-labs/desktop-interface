"""Opt-in integration against a dedicated synthetic AppKit window; never used in CI."""

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from desktop_interface import Backend, Desktop, Permission, Point, Size, WindowId


def wait_for(predicate, *, timeout=5):
    deadline = time.monotonic() + timeout
    while True:
        result = predicate()
        if result:
            return result
        if time.monotonic() >= deadline:
            raise TimeoutError("Synthetic fixture did not confirm the expected state")
        time.sleep(0.05)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compile-only", action="store_true")
    parser.add_argument("--window-control", action="store_true", help="move, resize, focus and minimize the fixture")
    parser.add_argument("--keyboard", action="store_true", help="submit synthetic text and physical keys to the focused fixture")
    parser.add_argument("--mouse", action="store_true", help="click, drag and scroll inside the fixture, restoring the pointer")
    parser.add_argument("--request-permissions", action="store_true", help="explicitly submit required permission requests")
    args = parser.parse_args()
    if sys.platform != "darwin":
        parser.error("The AppKit fixture requires macOS")
    with tempfile.TemporaryDirectory(prefix="desktop-interface-live-") as directory:
        work = Path(directory)
        binary = work / "DesktopInterfaceFixture"
        subprocess.run(["xcrun", "swiftc", str(Path(__file__).with_name("desktop_fixture.swift")),
                        "-module-cache-path", str(work / "modules"), "-framework", "AppKit",
                        "-o", str(binary)], check=True, timeout=120)
        if args.compile_only:
            print("Synthetic AppKit fixture compiled")
            return
        with Desktop() as desktop:
            topology = desktop.displays.snapshot()
            if not topology.displays:
                raise SystemExit("No active displays. Run this command from a Terminal in the logged-in GUI session.")
            if args.window_control or args.keyboard or args.mouse:
                if args.request_permissions:
                    desktop.permissions.request(Permission.ACCESSIBILITY)
                if not desktop.permissions.check(Permission.ACCESSIBILITY).granted:
                    raise SystemExit("Accessibility access is needed for fixture control/focus. Grant it to this process/host in System Settings and rerun.")
            if args.keyboard or args.mouse:
                if args.request_permissions:
                    desktop.permissions.request(Permission.POST_EVENTS)
                if not desktop.permissions.check(Permission.POST_EVENTS).granted:
                    raise SystemExit("Event-posting access is needed for input checks. Grant access and rerun.")
            state_path = work / "state.json"
            process = subprocess.Popen([str(binary), str(state_path)], stdout=subprocess.DEVNULL)
            try:
                def state():
                    if process.poll() is not None:
                        raise RuntimeError("Fixture exited before verification completed")
                    return json.loads(state_path.read_text()) if state_path.exists() else None

                initial = wait_for(state)
                if initial["pid"] != process.pid:
                    raise AssertionError("Fixture process identity differs")
                window = desktop.windows.get(WindowId(Backend.MACOS, initial["window_id"]))
                record = window.read()
                if record.process_id != process.pid or record.bounds is None:
                    raise AssertionError("Fixture window identity/bounds differ")
                result = {"displays": len(topology.displays), "fixture_identity": True}
                if args.window_control:
                    before = window.state()
                    try:
                        window.move(Point(record.bounds.x + 20, record.bounds.y + 20), timeout=2)
                        window.resize(Size(record.bounds.width + 20, record.bounds.height + 20), timeout=2)
                        window.focus(timeout=2)
                        window.minimize(timeout=2)
                        window.minimize(False, timeout=2)
                        result["window_control"] = True
                    finally:
                        window.minimize(False, timeout=2)
                        window.resize(record.bounds.size, timeout=2)
                        window.move(record.bounds.origin, timeout=2)
                        if before.minimized:
                            window.minimize(True, timeout=2)
                if args.keyboard:
                    from desktop_interface import Key
                    window.focus(timeout=2)
                    if not window.state().focused:
                        raise AssertionError("Fixture focus was lost before input")
                    for scalar in "Fixture 👋":
                        if not window.state().focused:
                            raise AssertionError("Fixture focus was lost during text check")
                        desktop.keyboard.type_text(scalar)
                    wait_for(lambda: state()["expected_text"])
                    before_keys = state()
                    if not window.state().focused:
                        raise AssertionError("Fixture focus was lost before key check")
                    desktop.keyboard.press(Key.SPACE)
                    wait_for(lambda: state()["key_downs"] > before_keys["key_downs"]
                             and state()["key_ups"] > before_keys["key_ups"])
                    result["keyboard_delivery"] = True
                if args.mouse:
                    from desktop_interface import ScrollUnit
                    window.focus(timeout=2)
                    saved = desktop.mouse.position()
                    def focused():
                        if not window.state().focused:
                            raise AssertionError("Fixture focus was lost before pointer check")
                    try:
                        focused()
                        start = Point(record.bounds.x + 80, record.bounds.y + 90)
                        end = Point(record.bounds.x + 160, record.bounds.y + 110)
                        desktop.mouse.move(start)
                        wait_for(lambda: desktop.mouse.position() == start)
                        before_mouse = state()
                        focused()
                        desktop.mouse.click()
                        wait_for(lambda: state()["clicks"] > before_mouse["clicks"]
                                 and state()["releases"] > before_mouse["releases"])
                        focused()
                        desktop.mouse.drag(end, duration=0.2)
                        wait_for(lambda: desktop.mouse.position() == end)
                        wait_for(lambda: state()["drags"] > before_mouse["drags"]
                                 and state()["releases"] >= before_mouse["releases"] + 2)
                        focused()
                        desktop.mouse.scroll(-2, unit=ScrollUnit.LINE)
                        wait_for(lambda: state()["scrolls"] > before_mouse["scrolls"])
                        result["mouse_delivery"] = True
                    finally:
                        desktop.mouse.move(saved)
                        wait_for(lambda: desktop.mouse.position() == saved)
                print(json.dumps(result, sort_keys=True))
            finally:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


if __name__ == "__main__":
    main()
