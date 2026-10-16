// Dedicated synthetic window for explicitly requested desktop integration checks.
import AppKit
import Foundation

final class Surface: NSView {
    var keyDowns = 0, keyUps = 0, clicks = 0, releases = 0, drags = 0, scrolls = 0
    var text = ""
    override var acceptsFirstResponder: Bool { true }
    override func draw(_ dirtyRect: NSRect) {
        NSColor.windowBackgroundColor.setFill()
        dirtyRect.fill()
        ("Desktop Interface Fixture\nSynthetic input is shown here.\n" + text as NSString).draw(
            at: NSPoint(x: 25, y: 60), withAttributes: [.font: NSFont.systemFont(ofSize: 20)])
    }
    override func keyDown(with event: NSEvent) {
        keyDowns += 1
        if text.utf16.count < 128 { text += event.characters ?? "" }
        needsDisplay = true
    }
    override func keyUp(with event: NSEvent) { keyUps += 1 }
    override func mouseDown(with event: NSEvent) { clicks += 1 }
    override func mouseUp(with event: NSEvent) { releases += 1 }
    override func mouseDragged(with event: NSEvent) { drags += 1 }
    override func scrollWheel(with event: NSEvent) { scrolls += 1 }
}

let application = NSApplication.shared
application.setActivationPolicy(.regular)
let window = NSWindow(contentRect: NSRect(x: 120, y: 120, width: 640, height: 420),
    styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
window.title = "Desktop Interface Fixture"
window.isReleasedWhenClosed = false
let surface = Surface(frame: NSRect(x: 0, y: 0, width: 640, height: 420))
window.contentView = surface
window.makeKeyAndOrderFront(nil)
window.makeFirstResponder(surface)
application.activate(ignoringOtherApps: true)
let output = URL(fileURLWithPath: CommandLine.arguments[1])
func publish() {
    // Only fixture identity, counts and an expected-text verdict leave the process.
    let state: [String: Any] = ["pid": ProcessInfo.processInfo.processIdentifier,
        "window_id": window.windowNumber, "key_downs": surface.keyDowns,
        "key_ups": surface.keyUps, "clicks": surface.clicks, "releases": surface.releases,
        "drags": surface.drags, "scrolls": surface.scrolls,
        "expected_text": surface.text == "Fixture 👋", "visible": window.isVisible]
    if let data = try? JSONSerialization.data(withJSONObject: state) {
        try? data.write(to: output, options: .atomic)
    }
}
publish()
let timer = Timer.scheduledTimer(withTimeInterval: 0.1, repeats: true) { _ in publish() }
application.run()
