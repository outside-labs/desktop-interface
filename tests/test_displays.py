"""Display geometry, snapshot consistency and ownership without desktop access."""

from dataclasses import FrozenInstanceError
from itertools import cycle
import unittest
from unittest.mock import Mock, patch

from desktop_interface import (
    AmbiguousTargetError, Backend, ClosedSessionError, Desktop, Display, DisplayId,
    DisplayTopology, DisplayTopologyChangedError, NativeCallError, PixelPoint,
    PixelSize, Point, Rect, StaleTargetError,
)
from desktop_interface._backends.macos.displays import MacOSDisplays
from desktop_interface._native import macos as native


def display(identifier=1, *, bounds=Rect(0, 0, 100, 50), pixels=PixelSize(200, 100), **kwargs):
    return Display(DisplayId(Backend.MACOS, identifier), bounds, pixels, **kwargs)


class DisplayGeometryTests(unittest.TestCase):
    def test_negative_origins_and_fractional_scale_round_trip(self):
        item = display(bounds=Rect(-100, -50, 100, 50), pixels=PixelSize(150, 75))
        self.assertEqual((item.scale_x, item.scale_y), (1.5, 1.5))
        point = Point(-90.5, -40.25)
        pixel = item.logical_to_pixel(point)
        self.assertEqual(pixel, PixelPoint(14.25, 14.625))
        self.assertEqual(item.pixel_to_logical(pixel), point)

    def test_rotated_display_pixels_are_already_in_desktop_orientation(self):
        item = display(bounds=Rect(-50, 0, 50, 100), pixels=PixelSize(100, 200), rotation=90)
        self.assertEqual(item.logical_to_pixel(Point(-40, 80)), PixelPoint(20, 160))
        self.assertEqual(item.pixel_to_logical(PixelPoint(20, 160)), Point(-40, 80))

    def test_half_open_edges_and_units_are_enforced(self):
        item = display()
        for point in (Point(100, 0), Point(0, 50), Point(-0.1, 0)):
            with self.assertRaises(ValueError):
                item.logical_to_pixel(point)
        for point in (PixelPoint(200, 0), PixelPoint(0, 100), PixelPoint(-1, 0)):
            with self.assertRaises(ValueError):
                item.pixel_to_logical(point)
        with self.assertRaises(TypeError):
            item.logical_to_pixel(PixelPoint(1, 1))
        with self.assertRaises(TypeError):
            item.pixel_to_logical(Point(1, 1))

    def test_overlapping_displays_require_explicit_selection(self):
        first, second = display(1), display(2, pixels=PixelSize(100, 50))
        topology = DisplayTopology(Backend.MACOS, (first, second))
        with self.assertRaises(AmbiguousTargetError):
            topology.logical_to_pixel(Point(10, 10))
        location = topology.logical_to_pixel(Point(10, 10), display_id=second.id)
        self.assertEqual(location.point, PixelPoint(10, 10))
        self.assertEqual(topology.pixel_to_logical(location), Point(10, 10))

    def test_pixel_location_cannot_be_reused_with_a_different_snapshot(self):
        first = DisplayTopology(Backend.MACOS, (display(),))
        second = DisplayTopology(Backend.MACOS, (display(),))
        location = first.logical_to_pixel(Point(10, 10))
        with self.assertRaises(StaleTargetError):
            second.pixel_to_logical(location)
        self.assertEqual(first.pixel_to_logical(location), Point(10, 10))

    def test_missing_or_mismatched_display_ids_are_explicit(self):
        topology = DisplayTopology(Backend.MACOS, (display(is_main=True),))
        self.assertEqual(topology.main, topology.displays[0])
        with self.assertRaises(StaleTargetError):
            topology.get(DisplayId(Backend.MACOS, 9))
        with self.assertRaises(ValueError):
            topology.get(DisplayId(Backend.WINDOWS, 1))
        with self.assertRaises(ValueError):
            topology.logical_to_pixel(Point(200, 200))
        with self.assertRaises(TypeError):
            topology.pixel_to_logical(PixelPoint(1, 2))
        self.assertIsNone(DisplayTopology(Backend.MACOS, ()).main)

    def test_invalid_topology_and_display_dimensions_fail(self):
        for make in (
            lambda: PixelSize(True, 2), lambda: PixelSize(1.5, 2),
            lambda: PixelSize(-1, 2), lambda: display(pixels=PixelSize(0, 2)),
            lambda: display(bounds=Rect(0, 0, 0, 2)),
            lambda: display(rotation=float("nan")),
            lambda: display(mirror_of=DisplayId(Backend.MACOS, 1)),
            lambda: DisplayTopology(Backend.MACOS, (display(), display())),
            lambda: DisplayTopology(Backend.MACOS, (display(1, is_main=True), display(2, is_main=True))),
            lambda: DisplayTopology(Backend.MACOS, [display()]),
            lambda: DisplayTopology(Backend.MACOS, (), captured_at=-1),
        ):
            with self.subTest(make=make):
                with self.assertRaises((TypeError, ValueError)):
                    make()

    def test_snapshot_records_are_immutable(self):
        item = display()
        with self.assertRaises(FrozenInstanceError):
            item.rotation = 90
        topology = DisplayTopology(Backend.MACOS, (item,))
        with self.assertRaises(FrozenInstanceError):
            topology.displays = ()


class NativeDisplayTests(unittest.TestCase):
    def reader(self, *, rotation=0, bounds=(0, 0, 100, 50), mode=(100, 50, 200, 100)):
        self.identifiers = [1]
        self.enumerations = 0

        def enumerate_displays(capacity, output, count):
            self.enumerations += 1
            if output is None:
                count._obj.value = len(self.identifiers)
            else:
                values = self.identifiers[:capacity]
                count._obj.value = len(values)
                for index, identifier in enumerate(values):
                    output[index] = identifier
            return 0

        self.release = Mock()
        self.functions = {
            "CGGetActiveDisplayList": Mock(side_effect=enumerate_displays),
            "CGDisplayIsActive": Mock(return_value=1),
            "CGDisplayIsOnline": Mock(return_value=1),
            "CGDisplayBounds": Mock(return_value=native.CGRect(native.CGPoint(*bounds[:2]), native.CGSize(*bounds[2:]))),
            "CGDisplayIsMain": Mock(side_effect=lambda identifier: identifier == 1),
            "CGDisplayRotation": Mock(return_value=rotation),
            "CGDisplayMirrorsDisplay": Mock(return_value=0),
            "CGDisplayCopyDisplayMode": Mock(return_value=900),
            "CGDisplayModeRelease": self.release,
            "CGDisplayModeGetWidth": Mock(return_value=mode[0]),
            "CGDisplayModeGetHeight": Mock(return_value=mode[1]),
            "CGDisplayModeGetPixelWidth": Mock(return_value=mode[2]),
            "CGDisplayModeGetPixelHeight": Mock(return_value=mode[3]),
        }
        reader = MacOSDisplays()
        reader.cg = Mock()
        reader.cg.bind.side_effect = lambda spec: self.functions[spec.name]
        return reader

    def test_stable_snapshot_reads_backing_pixels_and_releases_both_modes(self):
        reader = self.reader()
        topology = reader.snapshot()
        self.assertEqual(topology.displays, (display(is_main=True),))
        self.assertEqual(self.release.call_count, 2)
        self.assertEqual(self.release.call_args.args[0].value, 900)

    def test_quarter_turn_mode_dimensions_are_normalized_once(self):
        reader = self.reader(rotation=90, bounds=(-50, 0, 50, 100))
        item = reader.snapshot().displays[0]
        self.assertEqual(item.pixel_size, PixelSize(100, 200))
        self.assertEqual(item.logical_to_pixel(Point(-40, 80)), PixelPoint(20, 160))
        reader = self.reader(rotation=90, bounds=(0, 0, 50, 100), mode=(50, 100, 100, 200))
        self.assertEqual(reader.snapshot().displays[0].pixel_size, PixelSize(100, 200))

    def test_mode_is_released_if_metadata_becomes_invalid(self):
        reader = self.reader(mode=(0, 0, 0, 0))
        with self.assertRaises(DisplayTopologyChangedError):
            reader.snapshot()
        self.assertEqual(self.release.call_count, 3)

    def test_disconnected_display_has_bounded_retries(self):
        reader = self.reader()
        self.functions["CGDisplayIsActive"].return_value = 0
        with self.assertRaises(DisplayTopologyChangedError):
            reader.snapshot()
        self.assertEqual(self.functions["CGDisplayIsActive"].call_count, 3)
        self.functions["CGDisplayCopyDisplayMode"].assert_not_called()
        self.release.assert_not_called()

    def test_same_id_mode_change_is_retried_until_two_reads_agree(self):
        reader = self.reader()
        before, after = display(pixels=PixelSize(150, 75)), display()
        with patch.object(reader, "_ids", return_value=(1,)), \
             patch.object(reader, "_read", side_effect=[before, after, after, after]) as read:
            topology = reader.snapshot()
        self.assertEqual(topology.displays, (after,))
        self.assertEqual(read.call_count, 4)

    def test_changing_display_ids_exhaust_only_three_attempts(self):
        reader = self.reader()
        with patch.object(reader, "_ids", side_effect=cycle(((1,), (2,)))) as ids, \
             patch.object(reader, "_read", side_effect=lambda identifier: display(identifier)):
            with self.assertRaises(DisplayTopologyChangedError):
                reader.snapshot()
        self.assertEqual(ids.call_count, 6)

    def test_count_growth_during_enumeration_is_retried(self):
        reader = self.reader()
        original = self.functions["CGGetActiveDisplayList"].side_effect

        def grow(capacity, output, count):
            if self.enumerations == 2:
                self.identifiers = [1, 2]
            return original(capacity, output, count)

        self.functions["CGGetActiveDisplayList"].side_effect = grow
        self.assertEqual(len(reader.snapshot().displays), 2)

    def test_native_error_is_preserved_without_retry(self):
        reader = self.reader()
        self.functions["CGGetActiveDisplayList"].side_effect = None
        self.functions["CGGetActiveDisplayList"].return_value = 1001
        with self.assertRaises(NativeCallError) as error:
            reader.snapshot()
        self.assertEqual(error.exception.code, 1001)
        self.assertEqual(self.functions["CGGetActiveDisplayList"].call_count, 1)

    def test_unreasonable_counts_or_duplicate_ids_fail_before_unbounded_work(self):
        reader = self.reader()
        self.identifiers = list(range(1, 258))
        with self.assertRaises(NativeCallError):
            reader.snapshot()
        self.functions["CGDisplayCopyDisplayMode"].assert_not_called()
        self.identifiers = [1, 1]
        with self.assertRaises(NativeCallError):
            reader.snapshot()

    def test_headless_snapshot_is_valid(self):
        reader = self.reader()
        self.identifiers = []
        self.assertEqual(reader.snapshot().displays, ())


class DisplayManagerTests(unittest.TestCase):
    def test_managers_validate_before_native_work_and_reject_closed_sessions(self):
        with patch("sys.platform", "darwin"):
            desktop = Desktop()
        topology = DisplayTopology(Backend.MACOS, (display(),))
        with patch.object(desktop._backend, "display_snapshot", return_value=topology) as read:
            with self.assertRaises(TypeError):
                desktop.displays.get(1)
            with self.assertRaises(ValueError):
                desktop.displays.get(DisplayId(Backend.WINDOWS, 1))
            read.assert_not_called()
            self.assertEqual(desktop.displays.list(), topology.displays)
            self.assertEqual(desktop.displays.get(display().id), display())
            desktop.close()
            with self.assertRaises(ClosedSessionError):
                desktop.displays.snapshot()
        self.assertEqual(topology.logical_to_pixel(Point(10, 10)).point, PixelPoint(20, 20))


if __name__ == "__main__":
    unittest.main()
