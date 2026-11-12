ソースからのビルド手順と、途中で失敗した場合の処理を改善しました。

- **#3** Protonの取得前にoriginを登録し、Wineの相対URLを正しく解決します。
- **#4** 中断後に空のまま残ったsubmoduleを復元します。編集済みファイルは強制的に上書きしません。
- **#5** Podmanの警告とUIDを分けて読み取り、configureの数値判定が失敗する問題を修正しました。
- **#6** VRを含むビルドの順序、Go・Rust・ライセンス生成に必要な入力を追記しました。不足する入力はまとめて表示します。任意のKosmicKrispが失敗した場合は警告して続行し、DXMTのダウンロードには進捗表示と途中再開を追加しました。全体ビルドではゲストの生成後にアプリを作成します。
- **調査用** ソース版のVRランタイムに左右対称の姿勢調整機能を追加しました。動画については、ライブラリを変更せず初期化エラーを調べる診断ツールを追加しました。

**#1（動画・音声）と#2（VRの手のずれ）は調査中です。解消を確認した版ではありません。** 姿勢調整は既定で無効です。配布DMGには実験的なヘッドセットVRの部品を含めていないため、VR関連の変更を試す場合は[ソースからのビルド手順](https://github.com/r-fallingstar/steamac-lite/blob/v1.9.4-lite.14/docs/vr-guest.md)をご確認ください。

DMGはLite.13のマイク許可確認、日本語・中国語・韓国語の入力、更新機能を引き継いでいます。既存ユーザーはアプリ内の「アップデートを確認…」から更新できます。BOOTHのネットインストーラーもこの版を取得します。SteamOSのディスクと設定は保持します。

取得・復旧・UID判定・ビルドの継続/停止・HTTPダウンロード再開をテストしました。VRのネイティブ単体テストは587項目通過しました。フルビルドと実際のヘッドセットでの再検証は今回実施していません。

---

This release improves source builds and recovery after interrupted builds.

- **#3:** Register Proton's origin before fetching so Wine's relative submodule URL resolves correctly.
- **#4:** Restore empty submodule worktrees left after an interruption. Local edits are not force-overwritten.
- **#5:** Keep Podman warnings separate from the UID used by Proton's configure check.
- **#6:** Document the VR build order, Go/Rust setup and license inputs. Report missing inputs together, continue after an optional KosmicKrisp build fails, show DXMT download progress and resume partial downloads. The full build now assembles the app after the guest artifacts are ready.
- **Investigation tools:** Add opt-in mirrored controller calibration to the source VR runtime and a read-only decoder initialization probe.

**#1 (video/audio) and #2 (controller offsets) remain open. These problems are not confirmed fixed.** Controller calibration is off by default. The DMG does not include the experimental headset VR components. To test the VR changes, follow the [source-build steps](https://github.com/r-fallingstar/steamac-lite/blob/v1.9.4-lite.14/docs/vr-guest.md).

The DMG keeps Lite.13's microphone permission check, CJK input and app updater. Existing users can choose **Check for Updates…**. The BOOTH online installer also downloads this version. SteamOS disks and settings are kept.

Checkout recovery, UID checks, build continuation/failure and HTTP download resuming were tested. The native VR unit suite passed all 587 checks. A full source build and live headset test were not repeated for these changes.
