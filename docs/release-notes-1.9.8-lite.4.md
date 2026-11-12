# steamac Lite v1.9.8-lite.4

## 日本語

VRChatの動画再生で、固定した専用Protonランチャーから専用のFFmpeg 4.4.8を優先して使います。従来はゲームがSteam標準のFFmpeg avcodec58を読み込み、EPERMで失敗していました。Steam・Proton本体のファイルは変更しません。

訂正：以前のAVPro再生成功という記載を撤回します。作者のM1・RAM 8 GBのMacでは、インストール済みの通常版v1.9.8-lite.4で、Tokyo Sky HomeのYamaPlayer（AVPro）が引き続き黒画面・無音です。Unityの現在の再生状態はまだ再確認できていません。

デコーダーの優先順位修正は提供済みですが、単体でのデコーダー初期化成功や専用ライブラリの読込確認は、実際のAVPro再生成功を意味しません。AVProの黒画面・無音は未解決で、調査と[Issue #1](https://github.com/r-fallingstar/steamac-lite/issues/1)を継続します。複数スピーカーで音声が倍速になる件も引き続き調査中です。

同じアプリの標準アップデートです。カメラ転送・入力マイクの選択・レンダリング解像度（px）を引き継ぎ、既存のSteamOSディスク・ゲーム・設定を保持します。カメラの自動テスト5項目も通過しました。

「steamac Lite → アップデートを確認…」から更新できます。手動の場合は、[Releaseページ](https://github.com/r-fallingstar/steamac-lite/releases/tag/v1.9.8-lite.4)から **SteamAC-Lite-1.9.8-lite.4-macos-arm64.dmg** をダウンロードし、DMG内の **SteamAC Lite.app** を開いて「インストールして開く」を選んでください。既存の自動更新とBOOTHのネットインストーラーも最新版を取得します。

[導入ガイド](https://r-fallingstar.github.io/steamac-lite/?lang=ja) · [更新サポート](https://r-fallingstar.github.io/steamac-lite/support/?lang=ja)

## English

VRChat video playback now gives private FFmpeg 4.4.8 priority through a pinned private Proton launcher. The game previously loaded Steam’s stock FFmpeg avcodec58 and returned EPERM. Steam and Proton’s own files are unchanged.

Correction: the earlier claim of successful AVPro playback is withdrawn. On the owner’s M1 Mac with 8 GB RAM, Tokyo Sky Home’s YamaPlayer (AVPro) still shows a black screen with no audio in the installed standard v1.9.8-lite.4. Unity’s current playback status has not yet been reconfirmed.

The decoder-priority fix is delivered, but successful standalone decoder initialization and private-library mappings do not establish actual AVPro playback. AVPro’s black screen and missing audio remain unresolved; investigation continues and [Issue #1](https://github.com/r-fallingstar/steamac-lite/issues/1) stays open. There is no dedicated audio-speed patch or claim that the N-times-speed audio issue is fixed.

This is a standard update to the same app. It keeps camera forwarding, microphone selection, rendering resolution (px), and existing SteamOS disks, games and settings. All five automated camera regression cases passed.

Use **steamac Lite → Check for Updates…**. For a manual update, download **SteamAC-Lite-1.9.8-lite.4-macos-arm64.dmg** from the [release page](https://github.com/r-fallingstar/steamac-lite/releases/tag/v1.9.8-lite.4), open **SteamAC Lite.app** inside the DMG, and choose **Install and Open**. The existing updater and BOOTH online installer also obtain the latest release.

[Setup guide](https://r-fallingstar.github.io/steamac-lite/en/) · [Update support](https://r-fallingstar.github.io/steamac-lite/en/support/)

## 한국어

VRChat 동영상 재생 시 고정된 전용 Proton 런처를 통해 전용 FFmpeg 4.4.8을 우선 사용합니다. 이전에는 게임이 Steam 기본 FFmpeg avcodec58을 불러와 EPERM 오류로 실패했습니다. Steam과 Proton 본체의 파일은 변경하지 않습니다.

정정: 이전의 AVPro 재생 성공 주장을 철회합니다. 제작자의 M1·RAM 8 GB Mac에 설치된 표준 v1.9.8-lite.4에서도 Tokyo Sky Home의 YamaPlayer(AVPro)는 여전히 검은 화면이며 소리가 나오지 않습니다. Unity의 현재 재생 상태는 아직 다시 확인하지 못했습니다.

디코더 우선순위 수정은 제공되었지만, 독립 실행 진단의 디코더 초기화 성공과 전용 라이브러리 로드 확인이 실제 AVPro 재생 성공을 뜻하지는 않습니다. AVPro의 검은 화면·무음 문제는 미해결이며, 조사를 계속하고 [Issue #1](https://github.com/r-fallingstar/steamac-lite/issues/1)을 열린 상태로 유지합니다. 오디오 속도 전용 수정은 없으며 N배속 문제가 해결되었다고 주장하지 않습니다.

동일한 앱의 표준 업데이트입니다. 카메라 전달, 마이크 선택, 렌더링 해상도(px)와 기존 SteamOS 디스크·게임·설정을 유지합니다. 카메라 자동 회귀 테스트 5개 항목도 통과했습니다.

**steamac Lite → 업데이트 확인…**으로 업데이트할 수 있습니다. 수동으로 업데이트하려면 [릴리스 페이지](https://github.com/r-fallingstar/steamac-lite/releases/tag/v1.9.8-lite.4)에서 **SteamAC-Lite-1.9.8-lite.4-macos-arm64.dmg**를 다운로드하고, DMG 안의 **SteamAC Lite.app**을 열어 **설치 후 열기**를 선택하세요. 기존 자동 업데이트와 BOOTH 온라인 설치 프로그램도 최신 릴리스를 받습니다.

[설치 가이드](https://r-fallingstar.github.io/steamac-lite/ko/) · [업데이트 지원](https://r-fallingstar.github.io/steamac-lite/ko/support/)

## 简体中文

VRChat 视频播放现在通过固定的专用 Proton 启动器优先使用专用 FFmpeg 4.4.8。此前游戏会加载 Steam 自带的 FFmpeg avcodec58，并因 EPERM 错误而失败。Steam 和 Proton 本体文件保持不变。

更正：撤回此前关于 AVPro 播放成功的说法。在作者的 M1、8 GB 内存 Mac 上，已安装的标准版 v1.9.8-lite.4 中，Tokyo Sky Home 的 YamaPlayer（AVPro）仍然黑屏且无声音。Unity 当前的播放状态尚未重新确认。

解码器优先级修复已提供，但独立诊断中的解码器初始化成功及专用库加载确认，并不代表实际 AVPro 播放成功。AVPro 黑屏、无声音的问题仍未解决，将继续调查，并保持 [Issue #1](https://github.com/r-fallingstar/steamac-lite/issues/1) 开放。本版没有专门针对音频速度的修复，也不声称已解决 N 倍速音频问题。

这是同一应用的标准更新。保留摄像头转发、麦克风选择、渲染分辨率（px），以及已有的 SteamOS 磁盘、游戏和设置。摄像头自动回归测试的五个项目也已通过。

可通过 **steamac Lite → 检查更新…** 更新。手动更新时，请从[发布页面](https://github.com/r-fallingstar/steamac-lite/releases/tag/v1.9.8-lite.4)下载 **SteamAC-Lite-1.9.8-lite.4-macos-arm64.dmg**，打开 DMG 中的 **SteamAC Lite.app**，然后选择**安装并打开**。现有自动更新功能和 BOOTH 网络安装程序也会获取最新发布版本。

[安装指南](https://r-fallingstar.github.io/steamac-lite/zh-CN/) · [更新支持](https://r-fallingstar.github.io/steamac-lite/zh-CN/support/)
