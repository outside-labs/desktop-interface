"""Explicit, nonprompting native smoke checks with coarse output only."""

import argparse
import json

from desktop_interface import Desktop


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--permissions", action="store_true", help="Check existing grants without requesting access")
    args = parser.parse_args()
    if not args.permissions:
        parser.error("Choose an explicit native check, such as --permissions")
    with Desktop() as desktop:
        reports = desktop.permissions.check_all()
        if any(report.request_sent for report in reports):
            raise AssertionError("A nonprompting check submitted an access request")
        print(json.dumps({
            "backend": desktop.backend.value,
            "permissions": {report.permission.value: {
                "state": report.state.value, "support": report.support.value,
            } for report in reports},
        }, sort_keys=True))


if __name__ == "__main__":
    main()
