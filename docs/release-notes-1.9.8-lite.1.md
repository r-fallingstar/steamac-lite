steamac Liteを1.9.8-eac.1ベースへ更新しました。

- 「設定 → 音声」に入力マイクの選択を追加しました。選択は保存され、録音中にも切り替えられます。Mac全体の標準マイク設定は変更しません。
- 設定画面が画面内に収まるようにしました。長い項目はスクロールでき、ウィンドウのサイズも変更できます。
- 8GB向けのメモリ設定、4GiBのゲスト用スワップ、60Hz、日本語・中国語・韓国語入力、VRChat向け設定を引き継ぎます。スワップの二重作成を防ぎます。
- 本体部品を1.9.8の一式にそろえ、ソースと一致するゲストVRランタイムを同梱しました。ヘッドセットVRは既定で無効です。

M1・8GBでSteamの起動・終了、60Hz、CJK入力を確認しました。作者による内蔵マイク・設定画面の確認も完了しています。音声の自動テスト35件、VRランタイムの単体テスト587項目と通信テストを通過しました。M3での起動、USB/Bluetoothマイク、実際のヘッドセットは未検証です。Issue #1（動画・音声）と#2（手のずれ）は引き続き調査中です。

既存ユーザーは「steamac Lite → アップデートを確認…」から更新できます。BOOTHのネットインストーラーもこの版を取得します。SteamOSディスクと設定は保持します。起動できない場合はDMGを開き、「インストールして開く」を押してください。

[導入ガイド](https://r-fallingstar.github.io/steamac-lite/) · [更新サポート](https://r-fallingstar.github.io/steamac-lite/support/?lang=ja)

---

Updated to steamac 1.9.8-eac.1.

- Choose and save a microphone in Settings → Sound. You can switch while recording; the Mac's default input stays unchanged.
- Settings now fit within the screen, with scrolling and a resizable window.
- Keeps the 8GB profiles, one 4GiB guest swap file, 60Hz, CJK input and VRChat setup.
- Uses the 1.9.8 components and a source-matched guest VR runtime. Headset VR is off by default.

Steam startup/shutdown, 60Hz and CJK input were tested on M1/8GB. The author confirmed the built-in microphone and settings changes. Audio tests passed 35 checks; the VR runtime passed 587 unit checks and protocol tests. M3 startup, USB/Bluetooth microphones and a physical headset were not tested. Issues #1 and #2 remain open.

Use Check for Updates… in the app, or the BOOTH online installer. Your SteamOS disk and settings are kept. If the app does not open, download the DMG and choose Install and Open.

---

steamac 1.9.8-eac.1 기반으로 업데이트했습니다.

설정 → 사운드에서 입력 마이크를 선택하고 저장할 수 있습니다. 녹음 중에도 전환할 수 있으며 Mac의 기본 입력 설정은 바꾸지 않습니다. 설정 창은 화면 안에 표시되며 스크롤과 크기 조절을 지원합니다.

8GB용 메모리 설정, 4GiB 게스트 스왑, 60Hz, 중·일·한 입력과 VRChat용 설정을 유지합니다. M1·8GB에서 확인했으며 M3, USB/Bluetooth 마이크와 실제 VR 헤드셋은 미검증입니다. 이슈 #1·#2는 계속 조사 중입니다.

앱의 업데이트 확인 또는 BOOTH 온라인 설치 프로그램으로 업데이트할 수 있습니다. SteamOS 디스크와 설정은 유지됩니다.

---

已更新至 steamac 1.9.8-eac.1。

可在「设置 → 声音」中选择并保存输入麦克风，录音时也可切换，不会更改 Mac 的默认输入设置。设置窗口会保持在屏幕范围内，支持滚动和调整大小。

保留 8GB 内存配置、4GiB 客体交换文件、60Hz、中日韩输入和 VRChat 专用设置。已在 M1、8GB 上确认；M3、USB/蓝牙麦克风和实际 VR 头显尚未验证。Issue #1、#2 仍在调查中。

可通过应用内检查更新或 BOOTH 在线安装器更新，已有 SteamOS 磁盘和设置会保留。
