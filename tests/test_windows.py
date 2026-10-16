"""Bounded window discovery and owner-aware reads using synthetic metadata."""

from dataclasses import FrozenInstanceError, replace
import unittest
from unittest.mock import Mock, patch

from cf_fixture import CFHeap
from desktop_interface import (
    AmbiguousTargetError, Backend, ClosedSessionError, Desktop, NativeCallError,
    Rect, StaleTargetError, TargetNotFoundError, UnsupportedFeatureError,
    WindowId, WindowInfo,
)
from desktop_interface._backends.macos.windows import MacOSWindows


def info(identifier=7, pid=42, title="Fixture", **kwargs):
    return WindowInfo(WindowId(Backend.MACOS, identifier), pid, title=title, **kwargs)


class NativeWindowTests(unittest.TestCase):
    def reader(self, rows):
        self.heap = CFHeap()
        self.rows = [self.heap.row(**row) for row in rows]
        self.array = self.heap.add("array", self.rows)
        self.copy = Mock(side_effect=lambda options, relative: self.array)
        self.describe = Mock(side_effect=lambda identifiers: self.array)
        self.heap.functions["CGWindowListCopyWindowInfo"] = self.copy
        self.heap.functions["CGWindowListCreateDescriptionFromArray"] = self.describe
        reader = MacOSWindows()
        reader.cg = self.heap.library
        reader.cf.library = self.heap.library
        return reader

    def test_metadata_is_copied_with_unicode_nulls_and_optional_fields(self):
        reader = self.reader([{"title": "Fixture 👋\0tail", "owner": "Synthetic", "bounds": (-20, 30, 80, 60),
                               "layer": -1, "onscreen": True, "alpha": 0.5}])
        rows = reader.list(process_id=None, onscreen_only=True)
        self.assertEqual(rows, (info(title="Fixture 👋\0tail", owner_name="Synthetic", bounds=Rect(-20, 30, 80, 60),
                                     layer=-1, is_on_screen=True, alpha=0.5),))
        self.copy.assert_called_once_with(17, 0)
        self.assertEqual(self.heap.released, [self.array])

    def test_redacted_metadata_stays_absent_and_does_not_imply_permission(self):
        reader = self.reader([{}])
        row = reader.list(process_id=None, onscreen_only=False)[0]
        self.assertIsNone(row.title)
        self.assertIsNone(row.owner_name)
        self.assertIsNone(row.bounds)
        self.assertFalse(row.is_on_screen)
        self.copy.assert_called_once_with(16, 0)

    def test_pid_filter_skips_unselected_application_text_before_decoding(self):
        reader = self.reader([{"identifier": 1, "pid": 10, "title": "x" * 40000},
                              {"identifier": 2, "pid": 20, "title": "Fixture"}])
        rows = reader.list(process_id=20, onscreen_only=True)
        self.assertEqual([row.id.value for row in rows], [2])
        self.assertEqual(len(self.heap.text_reads), 1)

    def test_targeted_lookup_releases_input_and_output_arrays(self):
        reader = self.reader([{}])
        row = reader.get(WindowId(Backend.MACOS, 7), expected_process_id=42)
        self.assertEqual(row.id.value, 7)
        self.copy.assert_not_called()
        self.describe.assert_called_once()
        create = self.heap.functions["CFArrayCreate"]
        self.assertEqual(create.call_args.args[1][0], 7)
        self.assertEqual(create.call_args.args[2], 1)
        self.assertIsNone(create.call_args.args[3])
        self.assertEqual(len(self.heap.released), 2)
        self.assertEqual(self.heap.released[-1], self.array)

    def test_owner_change_is_rejected_without_decoding_replacement_text(self):
        reader = self.reader([{"pid": 99, "title": "x" * 40000}])
        with self.assertRaises(TargetNotFoundError):
            reader.get(WindowId(Backend.MACOS, 7), expected_process_id=42)
        self.assertEqual(self.heap.text_reads, [])
        self.assertEqual(len(self.heap.released), 2)

    def test_empty_array_is_distinct_from_unavailable_window_server(self):
        reader = self.reader([])
        self.assertEqual(reader.list(process_id=None, onscreen_only=True), ())
        self.copy.return_value = 0
        self.copy.side_effect = None
        with self.assertRaises(NativeCallError) as error:
            reader.list(process_id=None, onscreen_only=True)
        self.assertEqual(error.exception.operation, "CGWindowListCopyWindowInfo")

    def test_malformed_types_release_owner_without_unsafe_conversion(self):
        reader = self.reader([{}])
        fields = self.heap.object(self.rows[0])[1]
        fields[self.heap.key("kCGWindowOwnerPID")] = self.heap.add("string", "not a number")
        with self.assertRaises(NativeCallError):
            reader.list(process_id=None, onscreen_only=True)
        self.heap.functions["CFNumberGetValue"].assert_called_once()
        self.assertEqual(self.heap.released, [self.array])

    def test_wrong_bounds_type_never_reaches_native_geometry_decoder(self):
        reader = self.reader([{}])
        fields = self.heap.object(self.rows[0])[1]
        fields[self.heap.key("kCGWindowBounds")] = self.heap.add("string", "not a dictionary")
        with self.assertRaises(NativeCallError):
            reader.list(process_id=None, onscreen_only=True)
        self.heap.functions["CGRectMakeWithDictionaryRepresentation"].assert_not_called()
        self.assertEqual(self.heap.released, [self.array])

    def test_invalid_or_duplicate_ids_are_not_silently_accepted(self):
        for rows in ([{"identifier": 0}], [{"identifier": 1 << 40}], [{}, {}]):
            reader = self.reader(rows)
            with self.assertRaises(NativeCallError):
                reader.list(process_id=None, onscreen_only=True)
            self.assertEqual(self.heap.released, [self.array])
        reader = self.reader([{"identifier": -1}])
        self.assertEqual(reader.list(process_id=None, onscreen_only=True)[0].id.value, 0xFFFFFFFF)

    def test_bounded_array_and_string_sizes_fail_with_owned_cleanup(self):
        reader = self.reader([{}])
        self.heap.functions["CFArrayGetCount"].side_effect = None
        self.heap.functions["CFArrayGetCount"].return_value = 4097
        with self.assertRaises(NativeCallError):
            reader.list(process_id=None, onscreen_only=True)
        self.heap.functions["CFArrayGetValueAtIndex"].assert_not_called()
        self.assertEqual(self.heap.released, [self.array])
        reader = self.reader([{"title": "x" * 40000}])
        with self.assertRaises(NativeCallError):
            reader.list(process_id=None, onscreen_only=True)
        self.assertEqual(self.heap.released, [self.array])

    def test_invalid_number_bounds_or_alpha_report_native_metadata_failure(self):
        for row in ({"pid": -1}, {"alpha": float("nan")}, {"alpha": 1.5}, {"bounds": (0, 0, -1, 1)}):
            reader = self.reader([row])
            with self.assertRaises(NativeCallError):
                reader.list(process_id=None, onscreen_only=True)
            self.assertEqual(self.heap.released, [self.array])

    def test_native_id_width_is_validated_before_loading_or_allocation(self):
        reader = MacOSWindows()
        with patch("ctypes.CDLL", side_effect=AssertionError("Native load")):
            for identifier in (WindowId(Backend.WINDOWS, 7), WindowId(Backend.MACOS, 1 << 40)):
                with self.assertRaises(ValueError):
                    reader.get(identifier)

    def test_invalid_boolean_or_lossy_number_does_not_cross_a_wrong_native_type(self):
        reader = self.reader([{"pid": 1.5}])
        with self.assertRaises(NativeCallError):
            reader.list(process_id=None, onscreen_only=True)
        reader = self.reader([{}])
        fields = self.heap.object(self.rows[0])[1]
        fields[self.heap.key("kCGWindowIsOnscreen")] = self.heap.add("number", 1)
        with self.assertRaises(NativeCallError):
            reader.list(process_id=None, onscreen_only=True)
        self.heap.functions["CFBooleanGetValue"].assert_not_called()

    def test_utf8_size_and_partial_conversion_fail_without_exposing_text(self):
        for title in ("中" * 25000, "Fixture"):
            reader = self.reader([{"title": title}])
            if title == "Fixture":
                self.heap.functions["CFStringGetBytes"].side_effect = None
                self.heap.functions["CFStringGetBytes"].return_value = 0
            with self.assertRaises(NativeCallError) as error:
                reader.list(process_id=None, onscreen_only=True)
            self.assertNotIn(title, str(error.exception))
            self.assertEqual(self.heap.released, [self.array])

    def test_null_target_query_releases_only_allocated_input_array(self):
        reader = self.reader([])
        self.describe.side_effect = None
        self.describe.return_value = 0
        with self.assertRaises(NativeCallError):
            reader.get(WindowId(Backend.MACOS, 7))
        self.assertEqual(len(self.heap.released), 1)


class WindowManagerTests(unittest.TestCase):
    def session(self, rows):
        self.rows = list(rows)
        with patch("sys.platform", "darwin"):
            desktop = Desktop()

        def listed(*, process_id, onscreen_only):
            return tuple(row for row in self.rows if process_id is None or row.process_id == process_id)

        def read(window_id, *, expected_process_id=None):
            for row in self.rows:
                if row.id == window_id and (expected_process_id is None or row.process_id == expected_process_id):
                    return row
            raise TargetNotFoundError("Fixture target missing")

        desktop._backend.window_list = Mock(side_effect=listed)
        desktop._backend.window_info = Mock(side_effect=read)
        return desktop

    def test_duplicate_titles_require_disambiguation_and_match_exactly(self):
        desktop = self.session([info(1, 10), info(2, 20)])
        with self.assertRaises(AmbiguousTargetError):
            desktop.windows.find(title="Fixture")
        window = desktop.windows.find(process_id=20, title="Fixture")
        self.assertEqual(window.id.value, 2)
        with self.assertRaises(TargetNotFoundError):
            desktop.windows.find(title="fixture")

    def test_references_refresh_metadata_but_reject_disappearance_or_owner_change(self):
        desktop = self.session([info()])
        window = desktop.windows.get(info().id)
        self.rows = [replace(info(), title="Changed")]
        self.assertEqual(window.read().title, "Changed")
        self.assertEqual(window.initial.title, "Fixture")
        self.rows = [info(pid=99)]
        with self.assertRaises(StaleTargetError):
            window.read()
        self.rows = []
        with self.assertRaises(StaleTargetError):
            window.read()

    def test_public_reference_checks_identity_even_if_a_backend_is_inconsistent(self):
        desktop = self.session([info()])
        window = desktop.windows.get(info().id)
        desktop._backend.window_info.side_effect = None
        desktop._backend.window_info.return_value = info(pid=99)
        with self.assertRaises(StaleTargetError):
            window.read()

    def test_unknown_owners_can_be_listed_but_not_bound_to_a_reference(self):
        desktop = self.session([info(pid=None, title=None)])
        self.assertIsNone(desktop.windows.list()[0].process_id)
        with self.assertRaises(UnsupportedFeatureError):
            desktop.windows.get(info().id)
        with self.assertRaises(UnsupportedFeatureError):
            desktop.windows.find()

    def test_invalid_filters_fail_before_querying_and_closed_references_fail(self):
        desktop = self.session([info()])
        for operation in (
            lambda: desktop.windows.list(process_id=True),
            lambda: desktop.windows.list(onscreen_only=1),
            lambda: desktop.windows.find(title=1),
            lambda: desktop.windows.find(owner_name=1),
            lambda: desktop.windows.get(7),
            lambda: desktop.windows.get(WindowId(Backend.WINDOWS, 7)),
        ):
            with self.assertRaises((TypeError, ValueError)):
                operation()
        desktop._backend.window_list.assert_not_called()
        desktop._backend.window_info.assert_not_called()
        reference = desktop.windows.get(info().id)
        copied = desktop.windows.list()
        desktop.close()
        for operation in (desktop.windows.list, desktop.windows.find, reference.read,
                          lambda: desktop.windows.get(info().id)):
            with self.assertRaises(ClosedSessionError):
                operation()
        self.assertEqual(copied[0].title, "Fixture")

    def test_copied_records_are_immutable_and_validate_optional_fields(self):
        record = info()
        with self.assertRaises(FrozenInstanceError):
            record.title = "Changed"
        for overrides in ({"process_id": True}, {"process_id": -1}, {"title": 1},
                          {"bounds": (0, 0, 1, 1)}, {"is_on_screen": 1}, {"alpha": -1}):
            with self.assertRaises((TypeError, ValueError)):
                WindowInfo(**({"id": record.id, "process_id": 42} | overrides))


if __name__ == "__main__":
    unittest.main()
