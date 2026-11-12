steamac Lite v1.9.8-lite.3では、内蔵カメラの転送を標準版に追加しました。

- 設定の「音声」の隣に「カメラ」タブを追加しました。「ゲームで使うときだけカメラを起動」は既定でオンです。ゲームがカメラを要求すると撮影を始め、使用を終えると停止します。手動プレビューも利用できます。設定を閉じると手動プレビューを終了しますが、ゲームが使用中の自動撮影は続けます。
- 初回の案内でマイクとカメラの許可を確認します。許可だけでは撮影を始めません。許可が残っている場合は聞き直さず、更新などで以前の許可が外れた場合は再案内します。自動使用をオフにした選択や許可しなかった機能も聞き直しません。
- VRChatの「Tracking & IK → Selfie Expression」では、自動品質調整をオフにし、**Balanced（320 × 240・15 fps）**を選んでください。
- 「画面」に**レンダリング解像度（px）**のプリセットと、幅・高さのカスタム指定を追加しました。ウインドウの大きさとは別に設定できます。変更は設定画面の再起動操作で反映します。
- 入力マイクの選択、設定画面のスクロールとサイズ変更、起動時の更新確認、8 GB向け設定、CJK入力、VRChat向け設定を引き継ぎます。既存のSteamOSディスク・ゲーム・設定は保持します。

M1・RAM 8 GBのMacで、私が実験版camera.4でSelfie Expressionによる顔トラッキングと、ゲームで無効にした後のMacのカメラ自動停止を確認しました。この確認に基づき、カメラ機能を標準版へ取り込みます。すべてのカメラやMacでの動作を確認したものではありません。動画プレーヤー・音声の問題（Issue #1）とVRでの手のずれ（Issue #2）は引き続き調査中です。ヘッドセットVRは既定で無効です。

「steamac Lite → アップデートを確認…」から更新できます。手動で更新する場合は、[v1.9.8-lite.3のRelease](https://github.com/r-fallingstar/steamac-lite/releases/tag/v1.9.8-lite.3)から **SteamAC-Lite-1.9.8-lite.3-macos-arm64.dmg** をダウンロードし、「インストールして開く」を選んでください。

[導入ガイド](https://r-fallingstar.github.io/steamac-lite/) · [更新サポート](https://r-fallingstar.github.io/steamac-lite/support/?lang=ja)

---

steamac Lite v1.9.8-lite.3 adds built-in camera forwarding to the standard release.

- Settings now has a **Camera** tab next to **Sound**. Automatic camera use is on by default: capture starts when a game requests the camera and stops when the game releases it. Manual preview is also available. Closing Settings ends the manual preview; automatic capture continues if a game is still using the camera.
- The initial notice covers microphone and camera permissions. Granting access alone does not start capture. Existing grants are not requested again; if an update loses a previously granted permission, the app shows the notice again. Choices to leave automatic camera use off or decline access are kept.
- In VRChat **Tracking & IK → Selfie Expression**, turn off automatic quality adjustment and select **Balanced (320 × 240, 15 fps)**.
- Settings → Display includes rendering resolution presets in **px** and custom width and height, independently of the window size. Use the restart control in Settings to apply resolution changes.
- Keeps microphone selection, the resizable and scrollable settings window, startup update checks, 8 GB profiles, CJK input and VRChat setup. Existing SteamOS disks, games and settings are preserved.

On an M1 Mac with 8 GB RAM, I confirmed Selfie Expression face tracking and Mac camera auto-stop after disabling the camera in the game in experimental camera.4. That confirmation is the basis for bringing the camera feature into the standard app. It does not cover every camera or Mac. Video-player/audio issues (Issue #1) and VR hand alignment (Issue #2) remain under investigation. Headset VR is off by default.

Use **Check for Updates…** in the app. For a manual update, download **SteamAC-Lite-1.9.8-lite.3-macos-arm64.dmg** from the [v1.9.8-lite.3 release](https://github.com/r-fallingstar/steamac-lite/releases/tag/v1.9.8-lite.3) and choose **Install and Open**.

---

steamac Lite v1.9.8-lite.3 표준 버전에 내장 카메라 전달 기능을 추가했습니다.

- 설정의 **사운드** 옆에 **카메라** 탭을 추가했습니다. 게임이 요청할 때만 카메라를 켜는 자동 사용은 기본적으로 활성화되어 있습니다. 게임이 카메라를 요청하면 촬영을 시작하고 사용을 끝내면 중지합니다. 수동 미리보기도 가능합니다. 설정을 닫으면 수동 미리보기는 종료되지만, 게임이 사용 중인 자동 촬영은 계속됩니다.
- 최초 안내에서 마이크와 카메라 권한을 확인합니다. 권한을 허용하는 것만으로 촬영이 시작되지는 않습니다. 기존 권한이 유지되면 다시 묻지 않으며, 업데이트 등으로 이전 권한이 해제되면 다시 안내합니다. 자동 사용을 끄거나 권한을 허용하지 않은 선택도 유지합니다.
- VRChat의 **Tracking & IK → Selfie Expression**에서 자동 품질 조절을 끄고 **Balanced(320 × 240, 15 fps)**를 선택하세요.
- 설정 → 화면에 **px 단위 렌더링 해상도** 프리셋과 너비·높이 직접 지정을 추가했습니다. 창 크기와 별도로 설정합니다. 변경 사항은 설정 화면의 재시작 기능으로 적용합니다.
- 마이크 선택, 설정 창의 스크롤과 크기 조절, 시작 시 업데이트 확인, 8 GB용 설정, 중·일·한 입력과 VRChat용 설정을 유지합니다. 기존 SteamOS 디스크, 게임과 설정은 보존됩니다.

제 M1·RAM 8 GB Mac의 실험 버전 camera.4에서 Selfie Expression 얼굴 추적과 게임에서 카메라를 끈 뒤 Mac 카메라가 자동으로 중지되는 것을 확인했습니다. 이 확인을 바탕으로 표준 버전에 카메라 기능을 포함합니다. 모든 카메라와 Mac에서 확인한 것은 아닙니다. 동영상 플레이어·오디오 문제(Issue #1)와 VR 손 위치 문제(Issue #2)는 계속 조사 중입니다. 헤드셋 VR은 기본적으로 꺼져 있습니다.

앱의 **업데이트 확인…**으로 업데이트할 수 있습니다. 수동으로 업데이트하려면 [v1.9.8-lite.3 릴리스](https://github.com/r-fallingstar/steamac-lite/releases/tag/v1.9.8-lite.3)에서 **SteamAC-Lite-1.9.8-lite.3-macos-arm64.dmg**를 다운로드하고 **설치 후 열기**를 선택하세요.

---

steamac Lite v1.9.8-lite.3 标准版新增内置摄像头转发功能。

- 在设置的**声音**旁新增**摄像头**标签页。仅在游戏请求时启动摄像头的自动使用功能默认开启。游戏请求摄像头时开始采集，结束使用时停止。也可手动预览。关闭设置会结束手动预览；如果游戏仍在使用摄像头，自动采集会继续。
- 首次提示会确认麦克风和摄像头权限。仅授予权限不会开始采集。已有权限仍有效时不会重复询问；如果更新等操作导致先前的权限失效，会再次提示。关闭自动使用或未授予权限的选择也会保留。
- 在 VRChat 的 **Tracking & IK → Selfie Expression** 中关闭自动质量调整，并选择 **Balanced（320 × 240、15 fps）**。
- 在设置 → 显示中新增以 **px 为单位的渲染分辨率**预设，以及自定义宽度和高度。此设置独立于窗口大小。请使用设置界面的重新启动功能应用更改。
- 保留麦克风选择、设置窗口的滚动和大小调整、启动时检查更新、8 GB 内存配置、中日韩输入和 VRChat 专用设置。已有 SteamOS 磁盘、游戏和设置会保留。

我已在自己的 M1、8 GB 内存 Mac 的实验版 camera.4 中确认 Selfie Expression 面部追踪，以及在游戏中关闭摄像头后 Mac 摄像头自动停止。此次依据该确认将摄像头功能纳入标准版，并非已验证所有摄像头和 Mac。视频播放器及音频问题（Issue #1）和 VR 手部位置问题（Issue #2）仍在调查中。头显 VR 默认关闭。

可通过应用内的**检查更新…**更新。手动更新时，请从 [v1.9.8-lite.3 发布页面](https://github.com/r-fallingstar/steamac-lite/releases/tag/v1.9.8-lite.3)下载 **SteamAC-Lite-1.9.8-lite.3-macos-arm64.dmg**，然后选择**安装并打开**。
