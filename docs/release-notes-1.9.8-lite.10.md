# steamac Lite v1.9.8-lite.10

## 日本語

DXMTで動くゲームのフレームレートに上限を設けられるようになりました。画面に表示しきれない分のフレームを描かなくなるため、GPUの電力と発熱が減り、ファンのないMacでは速度低下が起きにくくなります。ゲーム本体やProton、EACには手を加えていません。

- **設定 > 画面 > ゲームのフレームレート上限**：OFF／30／60 fps。既定はOFFです。
- **設定 > 一般 > アプリがバックグラウンドのとき > ゲームのフレームレートを下げる**：OFF／30／15 fps。**既定は30 fps** です。ほかのアプリを操作している間、ゲームの描画をこのフレームレートまでに抑えます。ウインドウが完全に隠れているか最小化されている間は10 fpsになります。「ゲームを一時停止」と違いゲームは止まらないため、オンラインの接続は続きます。

どちらも変更するとすぐに反映されます。VRと、Vulkan経路で動くゲームには適用されません。60 Hzの画面では、30と60以外の値は表示のタイミングに合わず30 fpsになるため、選択肢をこの2つにしています。

開発時にM1・8GBのMacと検証用のディスクコピーで、VRChatのEAC認証とワールド入室を確認しました。上限なしでは45〜54 fps、上限30では30.0 fpsで安定し、VMプロセスのCPU使用率は約270%から約190%に下がりました。バックグラウンドでは約30 fpsになり、前面に戻すと元に戻りました。上限を切り替えたあとも切断はありませんでした。値は環境やワールドにより変わります。

Lite.9以降は「アップデートを確認…」から更新できます。既存のSteamOSディスクと設定は引き継ぎます。Lite.8以前は、DMGの「インストールして開く」で一度更新してください。

## English

Games running on DXMT can now be held to a frame-rate limit. Frames the display could never show are no longer drawn, which lowers GPU power and heat and helps fanless Macs avoid slowing down. The game, Proton and EAC are unchanged.

- **Settings > Display > Game frame rate limit**: Off / 30 / 60 fps. Off by default.
- **Settings > General > When steamac Lite is in the background > Lower the game's frame rate**: Off / 30 / 15 fps, **30 fps by default**. While another app is active the game draws at most this many frames, and 10 fps while the window is fully covered or minimized. Unlike "Pause the game", the game keeps running, so online sessions stay connected.

Both apply immediately. They do not apply in VR or to games on the Vulkan path. On a 60 Hz display other values land on 30 fps, so only 30 and 60 are offered.

Development checks on an M1 Mac with 8 GB RAM and a cloned disk covered VRChat's EAC session and world entry. Uncapped it ran at 45-54 fps; capped at 30 it held 30.0 fps and the VM process's CPU use fell from about 270% to about 190%. In the background it ran at about 30 fps and recovered when brought to the front, with no disconnect. Results depend on the Mac and the world.

Lite.9 or later updates through Check for Updates…. Existing SteamOS disks and settings are retained. From Lite.8 or earlier, update once with Install and Open in the DMG.
