#include <CoreGraphics/CoreGraphics.h>
#include <stdio.h>

int main(void) {
    CGDirectDisplayID displays[256];
    uint32_t count = 0;
    if (CGGetActiveDisplayList(0, NULL, &count) != kCGErrorSuccess || count > 256) {
        return 1;
    }
    if (CGGetActiveDisplayList(256, displays, &count) != kCGErrorSuccess || count > 256) {
        return 1;
    }
    puts("[");
    for (uint32_t index = 0; index < count; index++) {
        CGDirectDisplayID display = displays[index];
        CGRect bounds = CGDisplayBounds(display);
        CGDisplayModeRef mode = CGDisplayCopyDisplayMode(display);
        if (!mode) {
            return 1;
        }
        printf("%s{\"id\":%u,\"bounds\":[%.17g,%.17g,%.17g,%.17g],"
               "\"mode\":[%zu,%zu,%zu,%zu],\"rotation\":%.17g,"
               "\"main\":%u,\"mirror\":%u,\"active\":%u,\"online\":%u}",
               index ? "," : "", display,
               bounds.origin.x, bounds.origin.y, bounds.size.width, bounds.size.height,
               CGDisplayModeGetWidth(mode), CGDisplayModeGetHeight(mode),
               CGDisplayModeGetPixelWidth(mode), CGDisplayModeGetPixelHeight(mode),
               CGDisplayRotation(display), CGDisplayIsMain(display),
               CGDisplayMirrorsDisplay(display), CGDisplayIsActive(display), CGDisplayIsOnline(display));
        CGDisplayModeRelease(mode);
    }
    puts("\n]");
    return 0;
}
