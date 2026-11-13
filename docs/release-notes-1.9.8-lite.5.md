# steamac Lite v1.9.8-lite.5

## 日本語

VRChatの動画再生処理を更新しました。Wine MediaEngineの自動再生・ストリーム属性・フレームコピーを修正し、WineGStreamerにNV12のシステムメモリへのフォールバックを追加しました。

作者自身のM1・RAM 8 GBのMacで、診断をオフにした配布用の通常版v1.9.8-lite.5を確認しました。

- Tokyo Sky HomeのYamaPlayer（AVPro）で、[公開ライブURL](https://vrc.gate.vrtv.jp/live?p=g&u=d)（`https://vrc.gate.vrtv.jp/live?p=g&u=d`）の映像・音声・再生速度が正常でした。Stopとプレイリストの切り替えも確認しました。
- Unityの動画プレイヤーで、通常のYouTube動画が再生できることを確認しました。

これは作者の上記環境での確認です。すべてのMacやワールドでの動作を確認したものではありません。v1.9.8-lite.4でのAVPro黒画面・無音に関する訂正は、その版の確認結果として残ります。今回のv5で新たに再生を確認しました。

スピーカー数に応じて音声がN倍速になるという報告については、原因や発生条件をまだ切り分けられていません。今回の確認範囲では音声速度も正常でしたが、報告全体の解消を示すものではないため、[Issue #1](https://github.com/r-fallingstar/steamac-lite/issues/1)は開いたまま継続します。

同じアプリ・同じバンドルの標準アップデートです。既存の更新経路を使い、SteamOSディスク・ゲーム・設定を引き継ぎます。カメラなどの機能変更はありません。

既存の専用Protonの自動更新（schema 3 → 4）はクローン環境で検証しました。カメラ・COREと専用FFmpegの4ファイルが保持され、元の標準Protonの6ファイルが変わらないことを確認しています。Proton準備126件・メディア配置22件・FFmpegプロトコル34件のテストと、ネイティブアプリの自己テストが通過しました。

確認した配布用候補はソースコミット `61c3994`、`mfmediaengine.dll` のSHA-256先頭 `f15c`、`winegstreamer.dll` のSHA-256先頭 `0547` の組み合わせです。

更新は **steamac Lite → アップデートを確認…** から行えます。手動の場合は、[リリースページ](https://github.com/r-fallingstar/steamac-lite/releases/tag/v1.9.8-lite.5)から **SteamAC-Lite-1.9.8-lite.5-macos-arm64.dmg** を取得し、DMG内の **SteamAC Lite.app** を開いて **「インストールして開く」** を選んでください。BOOTHのネットインストーラーも自動で最新版を取得します。

## English

This update changes VRChat video playback. It fixes Wine MediaEngine autoplay, stream attributes and frame copying, and adds a system-memory fallback for NV12 in WineGStreamer.

The author checked the packaged standard v1.9.8-lite.5 with diagnostics off on their own M1 Mac with 8 GB RAM.

- In Tokyo Sky Home’s YamaPlayer (AVPro), video, audio and playback speed were normal using the [public live URL](https://vrc.gate.vrtv.jp/live?p=g&u=d) (`https://vrc.gate.vrtv.jp/live?p=g&u=d`). Stop and playlist switching were also checked.
- Ordinary YouTube video playback was confirmed in the Unity video player.

These checks cover the author’s setup above. They do not establish compatibility with every Mac or world. The correction about AVPro’s black screen and missing audio in v1.9.8-lite.4 remains a record of that version’s result. Playback was newly confirmed in v5.

The cause and conditions of the reported N-times-speed audio with multiple speakers have not yet been isolated. Audio speed was normal in these checks, but this does not establish that the reported problem is resolved generally. [Issue #1](https://github.com/r-fallingstar/steamac-lite/issues/1) stays open.

This is a standard update through the existing update channel for the same app and bundle. Existing SteamOS disks, games and settings are preserved. There are no changes to camera or other features.

The automatic upgrade of an existing private Proton from schema 3 to 4 was verified on a clone. Camera and CORE files and all four private FFmpeg files were preserved. Six original stock Proton files remained unchanged. All 126 Proton preparation tests, 22 media staging tests, 34 FFmpeg protocol tests and native app self-tests passed.

The checked production candidate uses source commit `61c3994`, with SHA-256 prefixes `f15c` for `mfmediaengine.dll` and `0547` for `winegstreamer.dll`.

Use **steamac Lite → Check for Updates…**. To update manually, download **SteamAC-Lite-1.9.8-lite.5-macos-arm64.dmg** from the [release page](https://github.com/r-fallingstar/steamac-lite/releases/tag/v1.9.8-lite.5), open **SteamAC Lite.app** inside the DMG and choose **Install and Open**. The BOOTH online installer also obtains the latest release automatically.

## 한국어

VRChat 동영상 재생 처리를 업데이트했습니다. Wine MediaEngine의 자동 재생·스트림 속성·프레임 복사를 수정하고, WineGStreamer에 NV12 시스템 메모리 폴백을 추가했습니다.

제작자 본인의 M1·RAM 8 GB Mac에서 진단을 끈 배포용 일반 버전 v1.9.8-lite.5를 확인했습니다.

- Tokyo Sky Home의 YamaPlayer(AVPro)에서 [공개 라이브 URL](https://vrc.gate.vrtv.jp/live?p=g&u=d)(`https://vrc.gate.vrtv.jp/live?p=g&u=d`)의 영상·오디오·재생 속도가 정상이었습니다. Stop과 재생 목록 전환도 확인했습니다.
- Unity 동영상 플레이어에서 일반 YouTube 동영상 재생을 확인했습니다.

확인 범위는 위 제작자 환경에 한정됩니다. 모든 Mac이나 월드에서 확인한 것은 아닙니다. v1.9.8-lite.4의 AVPro 검은 화면·무음에 관한 정정은 해당 버전의 확인 결과로 남습니다. 이번 v5에서 새로 재생을 확인했습니다.

스피커 수에 따라 오디오가 N배속이 된다는 보고는 원인과 발생 조건이 아직 분리되지 않았습니다. 이번 확인에서는 오디오 속도도 정상이었지만, 보고된 문제 전체의 해결을 뜻하지는 않습니다. [Issue #1](https://github.com/r-fallingstar/steamac-lite/issues/1)은 열린 상태로 유지합니다.

같은 앱·같은 번들의 표준 업데이트로 기존 업데이트 경로를 사용합니다. 기존 SteamOS 디스크·게임·설정을 유지합니다. 카메라 등 다른 기능의 변경은 없습니다.

기존 전용 Proton의 자동 업그레이드(schema 3 → 4)는 복제 환경에서 검증했습니다. 카메라·CORE와 전용 FFmpeg 파일 4개가 유지되었으며, 원본 기본 Proton 파일 6개도 변경되지 않았습니다. Proton 준비 테스트 126개·미디어 배치 테스트 22개·FFmpeg 프로토콜 테스트 34개와 네이티브 앱 자체 테스트가 통과했습니다.

확인한 배포용 후보는 소스 커밋 `61c3994`이며 SHA-256 접두사는 `mfmediaengine.dll`이 `f15c`, `winegstreamer.dll`이 `0547`입니다.

**steamac Lite → 업데이트 확인…**으로 업데이트할 수 있습니다. 수동 업데이트는 [릴리스 페이지](https://github.com/r-fallingstar/steamac-lite/releases/tag/v1.9.8-lite.5)에서 **SteamAC-Lite-1.9.8-lite.5-macos-arm64.dmg**를 받아 DMG 안의 **SteamAC Lite.app**을 열고 **설치 후 열기**를 선택하세요. BOOTH 온라인 설치 프로그램도 자동으로 최신 릴리스를 받습니다.

## 简体中文

本版更新了 VRChat 视频播放处理。修复了 Wine MediaEngine 的自动播放、流属性和帧复制，并为 WineGStreamer 增加 NV12 系统内存回退处理。

作者在自己的 M1、8 GB 内存 Mac 上，关闭诊断后检查了打包后的常规版 v1.9.8-lite.5。

- Tokyo Sky Home 的 YamaPlayer（AVPro）使用[公开直播 URL](https://vrc.gate.vrtv.jp/live?p=g&u=d)（`https://vrc.gate.vrtv.jp/live?p=g&u=d`）时，画面、声音和播放速度均正常。也确认了 Stop 和播放列表切换。
- 确认了 Unity 视频播放器可以播放普通 YouTube 视频。

上述确认仅覆盖作者的这一环境，并未验证所有 Mac 或世界。有关 v1.9.8-lite.4 中 AVPro 黑屏、无声的更正仍保留为该版本的验证记录。本次是在 v5 中新确认了播放成功。

对于音频随扬声器数量变成 N 倍速的报告，原因和触发条件仍未明确。本次检查中的音频速度正常，但这不能证明报告中的问题已普遍解决。[Issue #1](https://github.com/r-fallingstar/steamac-lite/issues/1)继续保持开放。

这是同一应用、同一应用包通过现有更新渠道提供的标准更新。保留已有的 SteamOS 磁盘、游戏和设置。摄像头等其他功能没有变更。

已在克隆环境中验证现有专用 Proton 的自动升级（schema 3 → 4）。摄像头、CORE 和 4 个专用 FFmpeg 文件均得到保留，6 个原始标准 Proton 文件也保持不变。126 项 Proton 准备测试、22 项媒体部署测试、34 项 FFmpeg 协议测试及原生应用自检均已通过。

已验证的生产候选版本使用源代码提交 `61c3994`。SHA-256 前缀分别为：`mfmediaengine.dll` 的 `f15c` 和 `winegstreamer.dll` 的 `0547`。

可通过 **steamac Lite → 检查更新…** 更新。手动更新时，请从[发布页面](https://github.com/r-fallingstar/steamac-lite/releases/tag/v1.9.8-lite.5)下载 **SteamAC-Lite-1.9.8-lite.5-macos-arm64.dmg**，打开 DMG 中的 **SteamAC Lite.app**，然后选择**安装并打开**。BOOTH 网络安装程序也会自动获取最新版本。
