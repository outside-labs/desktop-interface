"""A typed in-memory CoreFoundation fixture with no native object dereferences."""

import ctypes
from types import SimpleNamespace
from unittest.mock import Mock


class CFHeap:
    TYPES = {"array": 1, "dictionary": 2, "number": 3, "string": 4, "boolean": 5}

    def __init__(self):
        self.objects = {}
        self.keys = {}
        self.next_pointer = 1000
        self.released = []
        self.text_reads = []
        self.functions = {
            "CFRelease": Mock(side_effect=lambda pointer: self.released.append(self.address(pointer))),
            "CFGetTypeID": Mock(side_effect=lambda pointer: self.TYPES[self.object(pointer)[0]]),
            "CFArrayGetCount": Mock(side_effect=lambda pointer: len(self.object(pointer)[1])),
            "CFArrayGetValueAtIndex": Mock(side_effect=lambda pointer, index: self.object(pointer)[1][index]),
            "CFArrayCreate": Mock(side_effect=lambda alloc, values, count, callbacks: self.add("array", list(values[:count]))),
            "CFDictionaryGetValue": Mock(side_effect=lambda pointer, key: self.object(pointer)[1].get(self.address(key))),
            "CFNumberGetValue": Mock(side_effect=self.number),
            "CFBooleanGetValue": Mock(side_effect=lambda pointer: self.object(pointer)[1]),
            "CFStringGetLength": Mock(side_effect=self.length),
            "CFStringGetBytes": Mock(side_effect=self.bytes),
            "CGRectMakeWithDictionaryRepresentation": Mock(side_effect=self.bounds),
        }
        for kind, name in (("array", "CFArrayGetTypeID"), ("dictionary", "CFDictionaryGetTypeID"),
                           ("number", "CFNumberGetTypeID"), ("string", "CFStringGetTypeID"),
                           ("boolean", "CFBooleanGetTypeID")):
            self.functions[name] = Mock(return_value=self.TYPES[kind])
        self.library = SimpleNamespace(bind=self.bind, variable=self.variable)

    @staticmethod
    def address(pointer):
        return pointer.value if isinstance(pointer, ctypes.c_void_p) else pointer

    def object(self, pointer):
        return self.objects[self.address(pointer)]

    def add(self, kind, value):
        self.next_pointer += 1
        self.objects[self.next_pointer] = (kind, value)
        return self.next_pointer

    def key(self, name):
        if name not in self.keys:
            self.keys[name] = self.add("string", name)
        return self.keys[name]

    def variable(self, name, ctype):
        return ctype(self.key(name))

    def bind(self, spec):
        return self.functions[spec.name]

    def number(self, pointer, kind, output):
        value = self.object(pointer)[1]
        if kind == 4:
            if not isinstance(value, int) and not value.is_integer():
                return False
            value = int(value)
            if not -(1 << 63) <= value < 1 << 63:
                return False
        output._obj.value = value
        return True

    def length(self, pointer):
        self.text_reads.append(self.address(pointer))
        return len(self.object(pointer)[1].encode("utf-16-le")) // 2

    def bytes(self, pointer, span, encoding, loss, external, output, capacity, used):
        value = self.object(pointer)[1]
        payload = value.encode("utf-8")
        used._obj.value = len(payload)
        if output is not None:
            if len(payload) > capacity:
                return 0
            ctypes.memmove(output, payload, len(payload))
        return len(value.encode("utf-16-le")) // 2

    def bounds(self, pointer, output):
        x, y, width, height = self.object(pointer)[1]["rectangle"]
        output._obj.origin.x, output._obj.origin.y = x, y
        output._obj.size.width, output._obj.size.height = width, height
        return True

    def row(self, *, identifier=7, pid=42, title=None, owner=None, bounds=None,
            layer=None, onscreen=None, alpha=None):
        fields = {self.key("kCGWindowNumber"): self.add("number", identifier)}
        values = (("kCGWindowOwnerPID", "number", pid),
                  ("kCGWindowName", "string", title),
                  ("kCGWindowOwnerName", "string", owner),
                  ("kCGWindowLayer", "number", layer),
                  ("kCGWindowIsOnscreen", "boolean", onscreen),
                  ("kCGWindowAlpha", "number", alpha))
        for name, kind, value in values:
            if value is not None:
                fields[self.key(name)] = self.add(kind, value)
        if bounds is not None:
            fields[self.key("kCGWindowBounds")] = self.add("dictionary", {"rectangle": bounds})
        return self.add("dictionary", fields)
