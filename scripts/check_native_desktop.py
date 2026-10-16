"""Explicit, nonprompting native smoke checks with coarse output only."""

import argparse
import json
from pathlib import Path
import subprocess
import tempfile

from desktop_interface import Desktop, DisplayTopologyChangedError


def check_displays(desktop: Desktop) -> dict:
    """Compare against an independent SDK program without printing geometry."""
    with tempfile.TemporaryDirectory(prefix="desktop-interface-display-") as temporary:
        executable = Path(temporary) / "probe"
        source = Path(__file__).with_name("native_display_probe.c")
        subprocess.run(
            ["xcrun", "clang", "-std=c11", "-Werror", str(source),
             "-framework", "CoreGraphics", "-o", str(executable)], check=True, timeout=60,
        )
        for _ in range(3):
            try:
                snapshot = desktop.displays.snapshot()
            except DisplayTopologyChangedError:
                continue
            result = subprocess.run([str(executable)], capture_output=True, text=True, timeout=15)
            if result.returncode:
                continue
            expected = {item["id"]: item for item in json.loads(result.stdout)}
            if set(expected) != {item.id.value for item in snapshot.displays}:
                continue
            matches = True
            for item in snapshot.displays:
                record = expected[item.id.value]
                width, height, pixel_width, pixel_height = record["mode"]
                if (item.bounds.width, item.bounds.height) == (height, width) and width != height:
                    pixel_width, pixel_height = pixel_height, pixel_width
                matches &= (
                    record["bounds"] == [item.bounds.x, item.bounds.y, item.bounds.width, item.bounds.height]
                    and (pixel_width, pixel_height) == (item.pixel_size.width, item.pixel_size.height)
                    and record["rotation"] % 360 == item.rotation
                    and bool(record["main"]) is item.is_main
                    and record["mirror"] == (item.mirror_of.value if item.mirror_of else 0)
                    and bool(record["active"]) and bool(record["online"])
                )
            if matches:
                return {"count": len(snapshot.displays), "sdk_parity": True}
    raise AssertionError("Native display parity did not stabilize or a declaration differs from the SDK")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--permissions", action="store_true", help="Check existing grants without requesting access")
    parser.add_argument("--displays", action="store_true", help="Compare active display metadata against a native SDK probe")
    args = parser.parse_args()
    if not (args.permissions or args.displays):
        parser.error("Choose an explicit native check, such as --permissions")
    with Desktop() as desktop:
        output = {"backend": desktop.backend.value}
        if args.permissions:
            reports = desktop.permissions.check_all()
            if any(report.request_sent for report in reports):
                raise AssertionError("A nonprompting check submitted an access request")
            output["permissions"] = {report.permission.value: {
                "state": report.state.value, "support": report.support.value,
            } for report in reports}
        if args.displays:
            output["displays"] = check_displays(desktop)
        print(json.dumps(output, sort_keys=True))


if __name__ == "__main__":
    main()
