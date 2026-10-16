"""Exercise platform-neutral contracts before they reach native boundaries."""

from dataclasses import FrozenInstanceError
from fractions import Fraction
import itertools
import unittest

from desktop_interface import (
    Backend, Capability, DesktopError, DisplayId, Feature, NativeCallError,
    NativeLibraryError, NativeSymbolError, OperationTimeoutError,
    PermissionDeniedError, PermissionRequiredError, PermissionState, Point, Rect,
    Size, StaleTargetError, Support, UnsupportedFeatureError,
    UnsupportedPlatformError, WindowId,
)


class GeometryTests(unittest.TestCase):
    def test_fractional_and_negative_positions_are_preserved(self):
        self.assertEqual(Point(-20, Fraction(1, 2)), Point(-20.0, 0.5))
        self.assertEqual(Rect(-100, -50, 80, 20).origin, Point(-100, -50))
        self.assertEqual(Rect(-100, -50, 80, 20).size, Size(80, 20))

    def test_nonfinite_coordinates_and_extents_are_rejected(self):
        for bad in (float("inf"), float("-inf"), float("nan"), 10 ** 1000):
            for constructor in (
                lambda: Point(bad, 0), lambda: Point(0, bad),
                lambda: Size(bad, 1), lambda: Size(1, bad),
                lambda: Rect(bad, 0, 1, 1), lambda: Rect(0, bad, 1, 1),
                lambda: Rect(0, 0, bad, 1), lambda: Rect(0, 0, 1, bad),
            ):
                with self.subTest(value=str(bad)[:20], constructor=constructor):
                    with self.assertRaises(ValueError):
                        constructor()

    def test_nonreal_and_boolean_values_are_rejected(self):
        for bad in (True, False, "1", None, 1 + 0j, object()):
            for constructor in (lambda: Point(bad, 0), lambda: Size(1, bad), lambda: Rect(0, 0, bad, 1)):
                with self.subTest(value=bad):
                    with self.assertRaises(TypeError):
                        constructor()

    def test_negative_extents_and_overflowing_boundaries_are_rejected(self):
        for constructor in (
            lambda: Size(-1, 1), lambda: Size(1, -1),
            lambda: Rect(0, 0, -1, 1), lambda: Rect(0, 0, 1, -1),
            lambda: Rect(1e308, 0, 1e308, 1),
            lambda: Rect(0, 1e308, 1, 1e308),
        ):
            with self.subTest(constructor=constructor):
                with self.assertRaises(ValueError):
                    constructor()

    def test_containment_uses_half_open_edges(self):
        rect = Rect(-10, -20, 30, 40)
        for point, expected in (
            (Point(-10, -20), True), (Point(0, 0), True),
            (Point(19.99, 19.99), True), (Point(20, 0), False),
            (Point(0, 20), False), (Point(-10.01, 0), False),
        ):
            with self.subTest(point=point):
                self.assertIs(rect.contains(point), expected)

    def test_zero_area_has_no_contained_points_or_intersection(self):
        for empty in (Rect(0, 0, 0, 5), Rect(0, 0, 5, 0)):
            self.assertFalse(empty.contains(Point(0, 0)))
            self.assertIsNone(empty.intersection(Rect(0, 0, 5, 5)))

    def test_intersection_clips_shared_area_symmetrically(self):
        left, right = Rect(-20, -10, 30, 20), Rect(0, 0, 20, 20)
        self.assertEqual(left.intersection(right), Rect(0, 0, 10, 10))
        self.assertEqual(left.intersection(right), right.intersection(left))
        self.assertEqual(left.intersection(left), left)
        self.assertIsNone(left.intersection(Rect(10, 0, 10, 10)))
        self.assertIsNone(left.intersection(Rect(40, 40, 10, 10)))

    def test_geometry_methods_reject_untyped_arguments(self):
        with self.assertRaises(TypeError):
            Rect(0, 0, 1, 1).contains((0, 0))
        with self.assertRaises(TypeError):
            Rect(0, 0, 1, 1).intersection((0, 0, 1, 1))

    def test_geometry_is_immutable_and_hashable(self):
        for value, field in ((Point(1, 2), "x"), (Size(3, 4), "width"), (Rect(1, 2, 3, 4), "height")):
            with self.subTest(value=value):
                with self.assertRaises(FrozenInstanceError):
                    setattr(value, field, 99)
                self.assertEqual(len({value, value}), 1)


class IdentityTests(unittest.TestCase):
    def test_same_native_value_keeps_backend_and_kind_identity(self):
        self.assertNotEqual(WindowId(Backend.MACOS, 7), WindowId(Backend.WINDOWS, 7))
        self.assertNotEqual(WindowId(Backend.MACOS, 7), DisplayId(Backend.MACOS, 7))
        self.assertEqual(WindowId(Backend.MACOS, 7), WindowId(Backend.MACOS, 7))

    def test_invalid_identifiers_are_rejected(self):
        for kind in (DisplayId, WindowId):
            for value in (0, -1):
                with self.subTest(kind=kind, value=value):
                    with self.assertRaises(ValueError):
                        kind(Backend.MACOS, value)
            for value in (True, 1.0, "1", None):
                with self.subTest(kind=kind, value=value):
                    with self.assertRaises(TypeError):
                        kind(Backend.MACOS, value)
            with self.assertRaises(TypeError):
                kind("macos", 1)

    def test_identifiers_are_immutable_hash_keys(self):
        identifier = WindowId(Backend.MACOS, 7)
        self.assertEqual({identifier: "fixture"}[WindowId(Backend.MACOS, 7)], "fixture")
        with self.assertRaises(FrozenInstanceError):
            identifier.value = 8


class CapabilityTests(unittest.TestCase):
    def test_unknown_support_or_permission_never_grants_access(self):
        for support, permission in itertools.product(Support, PermissionState):
            report = Capability(Backend.MACOS, Feature.KEYBOARD_INPUT, support, permission)
            expected = support is Support.SUPPORTED and permission in (
                PermissionState.GRANTED, PermissionState.NOT_REQUIRED,
            )
            with self.subTest(support=support, permission=permission):
                self.assertIs(report.usable, expected)

    def test_defaults_are_conservative_and_reports_immutable(self):
        report = Capability(Backend.MACOS, Feature.SCREEN_CAPTURE, Support.SUPPORTED)
        self.assertIs(report.permission, PermissionState.UNKNOWN)
        self.assertFalse(report.usable)
        with self.assertRaises(FrozenInstanceError):
            report.permission = PermissionState.GRANTED

    def test_untyped_capability_states_are_rejected(self):
        fields = {
            "backend": Backend.MACOS, "feature": Feature.WINDOW_INFO,
            "support": Support.SUPPORTED, "permission": PermissionState.NOT_REQUIRED,
        }
        for field in fields:
            with self.subTest(field=field):
                with self.assertRaises(TypeError):
                    Capability(**(fields | {field: fields[field].value}))
        with self.assertRaises(TypeError):
            Capability(**fields, detail=123)


class ErrorTests(unittest.TestCase):
    def test_native_failure_preserves_zero_and_absent_status(self):
        error = NativeCallError("FixtureOperation", code=0)
        self.assertEqual(error.operation, "FixtureOperation")
        self.assertEqual(error.code, 0)
        self.assertIn("native code 0", str(error))
        self.assertIsNone(NativeCallError("FixtureOperation").code)
        self.assertEqual(str(NativeCallError("FixtureOperation")), "FixtureOperation failed")

    def test_expected_failures_share_one_catchable_base(self):
        for error in (
            UnsupportedPlatformError, UnsupportedFeatureError, PermissionRequiredError,
            PermissionDeniedError, NativeLibraryError, NativeSymbolError,
            NativeCallError, StaleTargetError, OperationTimeoutError,
        ):
            self.assertTrue(issubclass(error, DesktopError), error)
        self.assertTrue(issubclass(PermissionDeniedError, PermissionRequiredError))


if __name__ == "__main__":
    unittest.main()
