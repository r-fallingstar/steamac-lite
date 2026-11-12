# steamac Lite v1.9.8-lite.4

## 日本語

VRChatの動画再生で、固定した専用Protonランチャーから専用のFFmpeg 4.4.8を優先して使います。従来はゲームがSteam標準のFFmpeg avcodec58を読み込み、EPERMで失敗していました。Steam・Proton本体のファイルは変更しません。

作者のM1・RAM 8 GBのMacで、Tokyo Sky HomeのYamaPlayer（AVPro）とUnityの動画再生について、映像・音声・再生速度が正常であることを確認しました。

音声がN倍速になるという報告すべての解消を確認したものではありません。音声速度専用の修正はありません。[Issue #1](https://github.com/r-fallingstar/steamac-lite/issues/1)を報告した方は、この版で再確認をお願いします。Issueは未解決のまま継続します。

同じアプリの標準アップデートです。カメラ転送・入力マイクの選択・レンダリング解像度（px）を引き継ぎ、既存のSteamOSディスク・ゲーム・設定を保持します。カメラの自動テスト5項目も通過しました。

「steamac Lite → アップデートを確認…」から更新できます。手動の場合は、[Releaseページ](https://github.com/r-fallingstar/steamac-lite/releases/tag/v1.9.8-lite.4)から **SteamAC-Lite-1.9.8-lite.4-macos-arm64.dmg** をダウンロードし、DMG内の **SteamAC Lite.app** を開いて「インストールして開く」を選んでください。既存の自動更新とBOOTHのネットインストーラーも最新版を取得します。

[導入ガイド](https://r-fallingstar.github.io/steamac-lite/?lang=ja) · [更新サポート](https://r-fallingstar.github.io/steamac-lite/support/?lang=ja)

## English

VRChat video playback now gives private FFmpeg 4.4.8 priority through a pinned private Proton launcher. The game previously loaded Steam’s stock FFmpeg avcodec58 and returned EPERM. Steam and Proton’s own files are unchanged.

On an M1 Mac with 8 GB RAM, the owner confirmed normal video, audio and playback speed in Tokyo Sky Home’s YamaPlayer (AVPro) and Unity video playback.

This does not confirm that every reported N-times audio-speed issue is fixed. There is no dedicated audio-speed patch. The original [Issue #1](https://github.com/r-fallingstar/steamac-lite/issues/1) reporter is asked to retest this version. The issue stays open.

This is a standard update to the same app. It keeps camera forwarding, microphone selection, rendering resolution (px), and existing SteamOS disks, games and settings. All five automated camera regression cases passed.

Use **steamac Lite → Check for Updates…**. For a manual update, download **SteamAC-Lite-1.9.8-lite.4-macos-arm64.dmg** from the [release page](https://github.com/r-fallingstar/steamac-lite/releases/tag/v1.9.8-lite.4), open **SteamAC Lite.app** inside the DMG, and choose **Install and Open**. The existing updater and BOOTH online installer also obtain the latest release.

[Setup guide](https://r-fallingstar.github.io/steamac-lite/en/) · [Update support](https://r-fallingstar.github.io/steamac-lite/en/support/)

## 한국어

VRChat 동영상 재생 시 고정된 전용 Proton 런처를 통해 전용 FFmpeg 4.4.8을 우선 사용합니다. 이전에는 게임이 Steam 기본 FFmpeg avcodec58을 불러와 EPERM 오류로 실패했습니다. Steam과 Proton 본체의 파일은 변경하지 않습니다.

제작자의 M1·RAM 8 GB Mac에서 Tokyo Sky Home의 YamaPlayer(AVPro)와 Unity 동영상 재생의 영상·오디오·재생 속도가 정상임을 확인했습니다.

보고된 N배속 오디오 문제를 모두 해결했다고 확인한 것은 아닙니다. 오디오 속도 전용 수정은 없습니다. [Issue #1](https://github.com/r-fallingstar/steamac-lite/issues/1)을 처음 보고한 분은 이 버전으로 다시 확인해 주세요. 이슈는 미해결 상태로 유지합니다.

동일한 앱의 표준 업데이트입니다. 카메라 전달, 마이크 선택, 렌더링 해상도(px)와 기존 SteamOS 디스크·게임·설정을 유지합니다. 카메라 자동 회귀 테스트 5개 항목도 통과했습니다.

**steamac Lite → 업데이트 확인…**으로 업데이트할 수 있습니다. 수동으로 업데이트하려면 [릴리스 페이지](https://github.com/r-fallingstar/steamac-lite/releases/tag/v1.9.8-lite.4)에서 **SteamAC-Lite-1.9.8-lite.4-macos-arm64.dmg**를 다운로드하고, DMG 안의 **SteamAC Lite.app**을 열어 **설치 후 열기**를 선택하세요. 기존 자동 업데이트와 BOOTH 온라인 설치 프로그램도 최신 릴리스를 받습니다.

[설치 가이드](https://r-fallingstar.github.io/steamac-lite/ko/) · [업데이트 지원](https://r-fallingstar.github.io/steamac-lite/ko/support/)

## 简体中文

VRChat 视频播放现在通过固定的专用 Proton 启动器优先使用专用 FFmpeg 4.4.8。此前游戏会加载 Steam 自带的 FFmpeg avcodec58，并因 EPERM 错误而失败。Steam 和 Proton 本体文件保持不变。

作者已在自己的 M1、8 GB 内存 Mac 上确认 Tokyo Sky Home 的 YamaPlayer（AVPro）及 Unity 视频播放的画面、声音和播放速度均正常。

这不代表已确认解决所有已报告的 N 倍速音频问题。本版没有专门针对音频速度的修复。请 [Issue #1](https://github.com/r-fallingstar/steamac-lite/issues/1) 的原报告者使用此版本重新测试，该问题继续保持开放状态。

这是同一应用的标准更新。保留摄像头转发、麦克风选择、渲染分辨率（px），以及已有的 SteamOS 磁盘、游戏和设置。摄像头自动回归测试的五个项目也已通过。

可通过 **steamac Lite → 检查更新…** 更新。手动更新时，请从[发布页面](https://github.com/r-fallingstar/steamac-lite/releases/tag/v1.9.8-lite.4)下载 **SteamAC-Lite-1.9.8-lite.4-macos-arm64.dmg**，打开 DMG 中的 **SteamAC Lite.app**，然后选择**安装并打开**。现有自动更新功能和 BOOTH 网络安装程序也会获取最新发布版本。

[安装指南](https://r-fallingstar.github.io/steamac-lite/zh-CN/) · [更新支持](https://r-fallingstar.github.io/steamac-lite/zh-CN/support/)
