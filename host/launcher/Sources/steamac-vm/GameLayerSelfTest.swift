import CKrun
import AppKit
import QuartzCore

/// --selftest-game-layers: game layers cover the guest picture only while a game has focus.
/// The picture and non-Metal sublayers are untouched; the HUD follows the game/picture policy.
enum GameLayerSelfTest {
    static func run() -> Never {
        let parent = CAMetalLayer()
        let game = CAMetalLayer(), other = CALayer()
        parent.addSublayer(game)
        parent.addSublayer(other)
        var failures = 0
        func check(_ ok: Bool, _ what: String) {
            if !ok { failures += 1; log("selftest-game-layers: FAIL \(what)") }
        }
        VMView.applyGameLayers(visible: false, in: parent)
        check(game.isHidden, "game layer visible while the guest shows Steam")
        check(!other.isHidden && !parent.isHidden, "non-game layers hidden")
        check(game.animationKeys()?.isEmpty ?? true, "visibility change animated")
        VMView.applyGameLayers(visible: true, in: parent)
        check(!game.isHidden, "game layer hidden while the game has focus")
        func mode(_ layer: CAMetalLayer) -> String? { layer.developerHUDProperties?["mode"] as? String }
        VMView.applyHUD(true, gameVisible: true, main: parent, mainAttached: true)
        check(mode(game) == "default" && mode(parent) == "off", "HUD on with a game: not on the game layer only")
        VMView.applyHUD(true, gameVisible: false, main: parent, mainAttached: true)
        check(mode(game) == "off" && mode(parent) == "default", "HUD on without a game: not on the guest picture only")
        VMView.applyHUD(false, gameVisible: true, main: parent, mainAttached: true)
        check(mode(game) == "off" && mode(parent) == "off", "HUD off: still shown")
        let bare = CAMetalLayer()
        VMView.applyHUD(true, gameVisible: true, main: bare, mainAttached: true)
        check(mode(bare) == "default", "HUD on without game layers: not on the guest picture")
        let unattached = CAMetalLayer()
        VMView.applyHUD(false, gameVisible: false, main: unattached, mainAttached: false)
        check(mode(unattached) == nil, "picture HUD configured before its first on-screen drawable")
        PointerInput.configure()
        check(!NSEvent.isMouseCoalescingEnabled, "mouse coalescing still on after PointerInput.configure")
        // Bitmap size and hotspot follow gamescope before mapping into view points.
        func frame(window: CGSize, image: CGSize, hotspot: CGPoint = .zero,
                   shown: CGRect, flipped: Bool = false) -> CGRect {
            VMView.cursorFrame(position: CGPoint(x: window.width / 2, y: window.height / 2),
                               window: window, image: image, hotspot: hotspot, shown: shown,
                               parent: CGRect(x: 0, y: 0, width: 1200, height: 900), flipped: flipped)
        }
        let hd = CGSize(width: 1920, height: 1080)
        let letterbox = Renderer.fit(content: hd, in: CGRect(x: 0, y: 0, width: 1200, height: 900))
        check(frame(window: hd, image: CGSize(width: 256, height: 256), shown: letterbox)
                == CGRect(x: 600, y: 428, width: 23, height: 23), "256px theme cursor / letterbox")
        check(frame(window: hd, image: CGSize(width: 32, height: 32), shown: letterbox)
                == frame(window: hd, image: CGSize(width: 256, height: 256), shown: letterbox),
              "small game cursor and large theme cursor disagree")
        check(frame(window: hd, image: CGSize(width: 32, height: 32),
                    hotspot: CGPoint(x: 8, y: 16), shown: letterbox, flipped: true)
                == CGRect(x: 594, y: 439, width: 23, height: 23), "flipped Y / scaled hotspot")
        check(frame(window: CGSize(width: 2880, height: 1800), image: CGSize(width: 32, height: 32),
                    shown: CGRect(x: 0, y: 75, width: 1200, height: 750))
                == CGRect(x: 600, y: 420, width: 30, height: 30), "Retina window/view scale")
        check(frame(window: CGSize(width: 640, height: 480), image: CGSize(width: 32, height: 32),
                    shown: CGRect(x: 200, y: 150, width: 800, height: 600))
                == CGRect(x: 600, y: 405, width: 45, height: 45), "windowed / minimum cursor scale")
        check(frame(window: CGSize(width: 1000, height: 10000), image: CGSize(width: 32, height: 32),
                    shown: CGRect(x: 0, y: 0, width: 1000, height: 10000)).height == 256,
              "maximum cursor scale")
        check(frame(window: hd, image: CGSize(width: 256, height: 128),
                    hotspot: CGPoint(x: 128, y: 64), shown: letterbox)
                == CGRect(x: 589, y: 439, width: 23, height: 23), "oversized non-square bitmap / integer hotspot")

        _ = SteamacApplication.shared
        let view = VMView(frame: CGRect(x: 0, y: 0, width: 1200, height: 900),
                          renderer: Renderer(), contentPixelSize: hd)
        let overlayGame = CAMetalLayer()
        overlayGame.frame = view.bounds
        overlayGame.drawableSize = hd
        view.metalLayer.addSublayer(overlayGame)
        var tracking: [Bool] = []
        view.onCursorTrackingChange = { tracking.append($0) }
        view.gameLayersVisible = true
        view.guestCursorImage(width: 2, height: 2, xhot: 0, yhot: 0, bgra: Data(repeating: 255, count: 16))
        view.guestCursorPosition(x: 960, y: 540, windowWidth: 1920, windowHeight: 1080)
        view.guestCursorVisibility(true)
        check(view.cursorOverlayVisible && tracking == [true], "overlay did not appear above game")
        let overlay = view.metalLayer.sublayers?.first { $0.name == VMView.cursorLayerName }
        check(overlay != nil && (overlay?.animationKeys()?.isEmpty ?? true), "cursor image/position implicitly animated")
        view.guestCursorVisibility(false)
        check(!view.cursorOverlayVisible, "game hiding cursor leaves overlay visible")
        view.guestCursorVisibility(true)
        overlayGame.removeFromSuperlayer()
        // This is the existing wmtr_present_release_view notification, not a scanout redraw.
        view.setValue(true, forKey: "gameLayersVisible")
        check(!view.cursorOverlayVisible && tracking == [true, false], "wmtr release leaves stale overlay/tracking")
        check(overlay != nil && (overlay?.animationKeys()?.isEmpty ?? true), "cursor hiding implicitly animated")

        let progress = BootProgress()
        var images = 0, positions = 0, visible: [Bool] = [], ready = 0
        progress.onCursorImage = { w, h, _, _, data in
            images += 1
            check(w * h * 4 == data.count, "parser delivered wrong bitmap length")
        }
        progress.onCursorPosition = { _, _, _, _ in positions += 1 }
        progress.onCursorVisible = { visible.append($0) }
        progress.onCursorReady = { ready += 1 }
        let pixel = Data(repeating: 255, count: 4).base64EncodedString()
        progress.guestLine("cursor-image 1 1 -100 999 \(pixel)")
        progress.guestLine("cursor-image 256 256 0 0 \(Data(repeating: 0, count: 256 * 256 * 4).base64EncodedString())")
        for bad in ["0 1 0 0 \(pixel)", "257 1 0 0 \(pixel)", "\(Int.max) 2 0 0 \(pixel)",
                    "1 1 0 0 !", "2 2 0 0 \(pixel)", "1 1 0 0 \(pixel) extra"] {
            progress.guestLine("cursor-image \(bad)")
        }
        progress.guestLine("cursor-pos -5 10 1920 1080")
        progress.guestLine("cursor-pos 0 0 0 1080")
        progress.guestLine("cursor 1")
        progress.guestLine("cursor 0")
        progress.guestLine("cursor 2")
        progress.guestLine("cursor-ready")
        progress.guestLine("future-cursor-command ignored")
        check(images == 2 && positions == 1 && visible == [true, false] && ready == 1,
              "cursor protocol validation / forward compatibility")
        // Guest frames behind an opaque game layer stay in the mailbox and are shown once it hides.
        let display = DisplayBackend()
        let deferView = VMView(frame: CGRect(x: 0, y: 0, width: 640, height: 400),
                               renderer: Renderer(), contentPixelSize: CGSize(width: 640, height: 400))
        let presenter = Presenter(display: display, renderer: deferView.renderer)
        presenter.view = deferView
        // The guest picture; like libkrun (patch 0019) every frame buffer receives all of it, and
        // a frame changes only its damage rect.
        var picture = [UInt8](repeating: 0, count: 640 * 400 * 4)
        func guestFrame(_ value: UInt8, rect: DamageRect?) {
            let r = rect ?? DamageRect(x0: 0, y0: 0, x1: 640, y1: 400)
            for y in r.y0..<r.y1 { for x in r.x0..<r.x1 { for c in 0..<4 { picture[(y * 640 + x) * 4 + c] = value } } }
            let s = display.scanouts[0]
            guard let (id, ptr, len) = s.alloc() else { return check(false, "no free scanout buffer") }
            picture.withUnsafeBytes { ptr.copyMemory(from: $0.baseAddress!, byteCount: min(len, $0.count)) }
            check(s.present(frameId: id, rect: rect), "present rejected")
            presenter.consume()
        }
        _ = display.configureScanout(id: 0, displayWidth: 640, displayHeight: 400, width: 640, height: 400,
                                     format: UInt32(KRUN_DISPLAY_FORMAT_B8G8R8X8_UNORM))
        guestFrame(10, rect: nil)
        check(presenter.framesShown == 1 && presenter.framesDeferred == 0, "first frame not shown")
        let opaqueGame = CAMetalLayer()
        opaqueGame.frame = deferView.bounds
        opaqueGame.isOpaque = true
        opaqueGame.drawableSize = CGSize(width: 640, height: 400)
        deferView.metalLayer.addSublayer(opaqueGame)
        deferView.gameLayersVisible = true
        check(deferView.scanoutHidden, "opaque full-view game layer does not hide the scanout")
        guestFrame(20, rect: DamageRect(x0: 0, y0: 0, x1: 64, y1: 64))
        guestFrame(30, rect: DamageRect(x0: 100, y0: 100, x1: 200, y1: 200))
        check(presenter.framesShown == 1 && presenter.framesDeferred == 2, "hidden frames were uploaded")
        var resumed = false
        presenter.onNextFrame = { resumed = true }
        guestFrame(40, rect: DamageRect(x0: 0, y0: 0, x1: 8, y1: 8))
        check(resumed, "onNextFrame (resume chip) not run for a deferred frame")
        deferView.gameLayersVisible = false
        check(!deferView.scanoutHidden && presenter.framesShown == 2, "deferred frame not shown when the game hid")
        let shown = deferView.renderer.renderOffscreen(width: 640, height: 400)
        // (150,150) changed only in a deferred frame (30), (40,40) in frame 20, (4,4) in 40;
        // (300,300) kept frame 10's value. The catch-up upload must carry every deferred change.
        for (x, y, v) in [(150, 150, 30), (40, 40, 20), (4, 4, 40), (300, 300, 10)] as [(Int, Int, UInt8)] {
            let i = (y * 640 + x) * 4
            check(shown[i] == v && shown[i + 1] == v && shown[i + 2] == v,
                  "pixel \(x),\(y) is \(shown[i]) after catch-up, expected \(v)")
        }
        opaqueGame.isOpaque = false
        deferView.gameLayersVisible = true
        check(!deferView.scanoutHidden, "translucent game layer treated as hiding the scanout")
        guestFrame(50, rect: nil)
        check(presenter.framesShown == 3, "frame under a translucent game layer not shown")
        log(failures == 0 ? "selftest-game-layers: PASS" : "selftest-game-layers: \(failures) FAILED")
        exit(failures == 0 ? 0 : 1)
    }
}
