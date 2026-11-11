import AppKit
import Foundation

// Compile this main.swift with the unmodified DmgInstall.swift, InstallerCore.swift and
// UpdateInstallSupport.swift from the release tag. The capture bundle has a different ID
// and no VM code. It must live on a read-only volume to show the normal /Applications path.
enum Supervisor { static let isChild = false }
enum AppBundle { static var resources: String? { Bundle.main.resourcePath } }

guard let output = ProcessInfo.processInfo.environment["STEAMAC_GUIDE_CAPTURE"] else {
    fatalError("STEAMAC_GUIDE_CAPTURE must name an output PNG")
}
let timer = Timer(timeInterval: 1, repeats: true) { timer in
    MainActor.assumeIsolated {
        guard let window = NSApp.windows.first(where: { $0.isVisible && $0.contentView != nil }) else { return }
        timer.invalidate()
        guard let frame = window.contentView?.superview else { exit(1) }
        frame.layoutSubtreeIfNeeded()
        let size = frame.bounds.size
        let scale = window.backingScaleFactor
        guard let bitmap = NSBitmapImageRep(bitmapDataPlanes: nil,
            pixelsWide: Int(size.width * scale), pixelsHigh: Int(size.height * scale),
            bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
            colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0) else { exit(1) }
        bitmap.size = size
        frame.cacheDisplay(in: frame.bounds, to: bitmap)
        // Native alert materials have a transparent backdrop in a view snapshot. Render
        // onto the native window background so the exported asset is readable on any site.
        let canvas = NSBitmapImageRep(bitmapDataPlanes: nil,
            pixelsWide: bitmap.pixelsWide, pixelsHigh: bitmap.pixelsHigh,
            bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
            colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
        canvas.size = size
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: canvas)
        NSColor.windowBackgroundColor.setFill()
        NSRect(origin: .zero, size: size).fill()
        NSImage(cgImage: bitmap.cgImage!, size: size).draw(in: NSRect(origin: .zero, size: size))
        NSGraphicsContext.restoreGraphicsState()
        guard let png = canvas.representation(using: .png, properties: [:]) else { exit(1) }
        do { try png.write(to: URL(fileURLWithPath: output)) }
        catch { fputs("\(error)\n", stderr); exit(1) }
        print("Saved cursor-free native dialog: " + output)
        exit(0)
    }
}
RunLoop.main.add(timer, forMode: .common)
MainActor.assumeIsolated { DmgInstall.runIfNeeded(CommandLine.arguments) }
fatalError("The capture bundle must be launched from a read-only volume")
