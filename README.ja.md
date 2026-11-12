# steamac Lite

[English](README.md) · **日本語**

**[写真付きの導入ガイド](https://r-fallingstar.github.io/steamac-lite/)** · [更新サポート](https://r-fallingstar.github.io/steamac-lite/support/?lang=ja) — ダウンロードからVRChat向け設定まで、実画面で案内します。

[日本語](https://r-fallingstar.github.io/steamac-lite/?lang=ja) · [English](https://r-fallingstar.github.io/steamac-lite/en/) · [한국어](https://r-fallingstar.github.io/steamac-lite/ko/) · [简体中文](https://r-fallingstar.github.io/steamac-lite/zh-CN/)

Apple Silicon・RAM 8 GBのMac向けに、[StonkGuy/steamac](https://github.com/StonkGuy/steamac)の`v1.9.8-eac.1`から作成した実験版です。Mac上の仮想マシンでSteamOSを動かし、FEX・Proton・DXMTを利用します。

**[アプリをダウンロード（M1以降のMac用DMG）](https://github.com/r-fallingstar/steamac-lite/releases/download/v1.9.8-lite.4/SteamAC-Lite-1.9.8-lite.4-macos-arm64.dmg)**

初回の案内ではマイクとカメラの許可を確認します。許可が残っていれば聞き直さず、更新などで以前の許可が外れた場合は再案内します。自動使用をオフにした選択や許可しなかった機能も聞き直しません。Lite.6の録音処理の修正も含みます。[原因と確認内容](docs/microphone-fix.md)。

DMG内の **SteamAC Lite.app** を開き、**「インストールして開く」** を押すと、アプリケーションフォルダへ自動でコピーして起動します。ビルドは不要です。[はじめての導入手順](docs/quick-start.ja.md) · [Releaseと更新内容](https://github.com/r-fallingstar/steamac-lite/releases/tag/v1.9.8-lite.4)

macOS 15.5以降・Apple Silicon向けです。この実験版はApple未公証で、初回起動時の案内は導入手順に記載しています。SteamOS・ゲームは別途ダウンロードします。初回の「VRChat向け設定」で、FEXの導入・Protonの選択・起動オプションを自動で設定できます。Steamへのログインと、Steamに表示されるダウンロード確認は本人が操作します。[設定の流れ](docs/vrchat-setup.ja.md)を参照してください。

Lite.9以降は新しいReleaseをアプリ内で通知します。「アップデート」で取得し、「更新して開き直す」で反映します。SteamOSのディスクと設定は引き継ぎます。Lite.8以前は最初の1回だけ手動でLite.9以降へ更新してください。[更新のしくみ](docs/in-app-updates.md)。

## v1.9.8-lite.4

VRChatの動画再生で、固定した専用Protonランチャーから専用のFFmpeg 4.4.8を優先して使うようにしました。従来はゲームがSteam標準のFFmpeg avcodec58を読み込み、EPERMで失敗していました。Steam・Proton本体のファイルは変更しません。

訂正：以前のAVPro再生成功という記載を撤回します。作者のM1・RAM 8 GBのMacでは、インストール済みの通常版v1.9.8-lite.4で、Tokyo Sky HomeのYamaPlayer（AVPro）が引き続き黒画面・無音です。旧版での結果ではありません。Unityの現在の再生状態はまだ再確認できていません。デコーダーの優先順位修正は提供済みですが、単体でのデコーダー初期化成功や専用ライブラリの読込確認は、実際のAVPro再生成功を意味しません。AVPro再生は未解決で、調査と[Issue #1](https://github.com/r-fallingstar/steamac-lite/issues/1)を継続します。音声速度専用の修正はなく、N倍速問題の解消も主張しません。現時点では報告者への再テストはお願いしません。

同じアプリの標準アップデートです。カメラ転送・入力マイクの選択・レンダリング解像度（px）、既存のSteamOSディスク・ゲーム・設定を引き継ぎます。カメラの自動テスト5項目も通過しました。「アップデートを確認…」、またはDMGの「インストールして開く」で更新できます。既存の自動更新とBOOTHのネットインストーラーも最新版を取得します。[更新内容](docs/release-notes-1.9.8-lite.4.md)。

## v1.9.8-lite.3

標準版に内蔵カメラの転送を追加しました。設定の「音声」の隣に「カメラ」タブがあります。「ゲームで使うときだけカメラを起動」は既定でオンです。ゲームがカメラを要求すると撮影を始め、使用を終えると停止します。許可だけでは撮影しません。手動プレビューも利用でき、設定を閉じるとプレビューを終了します。ゲームが使用中の場合は自動撮影を続けます。

VRChatの「Tracking & IK → Selfie Expression」では自動品質調整をオフにして、**Balanced（320 × 240・15 fps）**を選んでください。「画面」には**レンダリング解像度（px）**のプリセットと、幅・高さのカスタム指定を追加しました。ウインドウの大きさとは別の設定です。変更は設定画面の再起動操作で反映します。

M1・RAM 8 GBのMacで、利用者が実験版camera.4のSelfie Expressionによる顔トラッキングと、ゲームで無効にした後のMacのカメラ自動停止を確認しました。このカメラ機能を標準版へ取り込みます。すべてのカメラやMacの動作を保証するものではありません。動画プレーヤー・音声とヘッドセットVRの問題は引き続き調査中です。既存のSteamOSディスク・ゲーム・設定、入力マイクの選択、設定画面のスクロールとサイズ変更は引き継ぎます。[更新内容](docs/release-notes-1.9.8-lite.3.md)を参照してください。

## このForkの変更

| 項目 | Liteの既定値・動作 |
|---|---|
| VMのRAM | Macに応じて3〜16 GiB。8 GBでは3 GiB |
| ゲスト用ディスクスワップ | 8 GB向け設定では`/home`のext4上に4 GiB。既存のzramは維持 |
| 初期描画 | MacのRAMと画面に合わせて960×600〜1920×1200。Retinaなし、60 Hz |
| 手動設定 | 設定画面で自動・軽量・手動を選択。個別に選んだ値を優先 |
| 表示言語 | 初回起動で日本語・英語・韓国語・簡体字中国語・ロシア語を選択 |
| 描画経路 | DXMTを優先。利用できなければVulkan |
| キーボード | Macの物理配列から起動時にUS/JISを自動判別 |
| 文字入力 | 日本語・中国語（ピンイン）・韓国語（2ボル式）を初回に設定。追加ダウンロード不要 |
| アプリ・設定 | `SteamAC Lite.app`として通常版と別に保存 |

macOSの仮想メモリ設定は変更しません。スワップはRAM不足による終了を減らすための補助で、物理RAMやGPUメモリを増やすものではありません。頻繁なスワップは遅くなります。**60 Hzは画面更新の設定であり、ゲーム内60 fpsの保証ではありません。**

[Mac別の自動設定表と設定方法](docs/performance-profiles.md)

初回に「日本語」を選ぶと、ランチャーの設定画面やメニューを日本語で表示します。Lite.5以降は、新しいSteamOSディスクのSteamも初回から日本語で表示します。既存ディスクのSteamの言語は変更しません。ランチャーは **設定… > 一般 > 表示言語** で変更し、アプリの再起動で反映します。Steamとゲームの言語はそれぞれの設定で変更します。

## 日本語の入力

必要に応じてControl＋.で日本語（Anthy）を選んでから入力します。

1. テキスト欄を選びます。初回は英数入力で始まります。
2. **Control＋Space**で英数・日本語を切り替えます。JISでは**かな**でひらがな、**英数**で直接入力へ切り替えられます。
3. ローマ字で入力し、**Space**で漢字変換、**Enter**で確定します。

配列はmacOSの表示言語やATOK等の入力ソースから推測せず、物理キーボード情報を使います。外付けキーボードを変更した場合はアプリを再起動してください。ISOの形状も判別しますが、地域別の英独仏配列までは自動推定しません。複数配列の同時利用や特殊なリマップ環境には制限があります。

詳しい設定と手動指定は[日本語入力と配列](docs/japanese-input.md)にあります。

中国語はShift、韓国語はControl＋Spaceで英数入力と切り替えます。Control＋.で入力方式を変更できます。初回は表示言語と物理配列とは別にMacの入力ソースを判別します。ABC/USなら直接英数、対応する日本語・ピンイン・2ボル式ならその入力方式を英数モードで用意します。判別できない場合は直接英数です。既存のSteamOS入力設定は保持します。

## ビルドと起動

Lite用の組み立てには、`scripts/lite/base-release.json`で固定した`FX Steam Launcher.app` 1.9.8-eac.1、Swift 6、SDK、Git、Python 3、erofs-utils、Rust 1.90.0が必要です。`BASE_APP`で指定する本体は同ファイルのハッシュで検証します。

動画ライブラリは`guest/video/build-codecs.sh`で、固定したFFmpeg 4.4.8のソースとSDKから作成します。Dockerを使用するビルド中はSteamOSを停止してください。[動画の検証内容](docs/vrchat-video-investigation.md)も参照してください。

先に`guest/vr`をx86_64 LinuxのSteam Runtime sniper環境でビルドし、`make check`を完了してください。`work/out/vr/runtime/bin/linux64/`には`vrclient.so`と`runtime-build.json`が必要です。記録は`source_tree`（`git rev-parse HEAD:guest/vr`）、`sha256`、`unit_tests_passed`、`end_to_end_tests_passed`を含み、実際の成果物と試験結果に対応させます。ソースや試験が不一致の場合、組み立ては停止します。

```sh
export BASE_APP="/path/to/FX Steam Launcher.app"
python3 scripts/test/low-memory-swap.py
python3 scripts/test/keyboard-setup.py
bash scripts/lite/build-audio-library.sh
bash guest/video/build-codecs.sh
LIBKRUN_OVERRIDE="$PWD/work/out/host/lib/libkrun.1.dylib" bash scripts/lite/build-app.sh
```

全コンポーネントをソースから作る場合は[ビルド要件](docs/upstream/requirements-and-building.md)と[VRのビルド順序](docs/vr-guest.md)を参照してください。1.9.8-lite.2のDMGは、固定した上流のVR部品に、このForkからビルド・検証したゲストVRランタイムを組み合わせています。ヘッドセットでの動作確認とは別です。

出力は`work/out/SteamAC Lite.app`です。元の署名付きアプリのカーネル・グラフィックス等を再利用し、変更したランチャーとゲスト設定を組み込みます。全コンポーネントをソースから構築するリリース手順とは異なります。

停止済みのSteamOSディスクのコピーで試してください。同じディスクを複数のVMから同時に開かないでください。初回のスワップ作成時には、Mac・ゲストにそれぞれ8 GiB以上の空き容量が必要です。「VRChat向け設定」は既定で有効です。Steamへのログイン後、必要なツールのダウンロードが終わると追加設定を適用し、Steamを一度再起動します。VRChatは自動では起動しません。

[ビルド手順とメモリ配分の詳細](docs/8gb-profile.md) · [上流のゲーム設定](SETUP.md)

## 動作確認の範囲

Apple M1・RAM 8 GiB・macOS 27.2で、Steamの画面表示と正常終了、3 GiBのVM RAM、4 GiBのゲスト用スワップを確認しました。作者の同環境でVRChatの動作も確認しました。FPSや長時間の安定性、すべてのワールド・アバターの互換性は未確認です。

Lite.5では、新しいSteamOSディスクの作成から、FEX・Proton・EACのダウンロード、VRChat向け設定の完了まで確認しました。Steamへのログインとインストール確認は手動です。別の未起動SteamOSディスクで、Steamの初回ログイン画面が日本語になることも確認しています。[検証結果と制限](docs/validation-lite.5.md)を参照してください。

配列・日本語入力の確認方法は[日本語入力と配列](docs/japanese-input.md)を参照してください。上流版の最低RAM要件は16 GBで、この8 GBプロファイルは独自の実験です。Valve、VRChat、Epic Games、FX GAMES等の公式製品ではありません。元のライセンス・noticeは保持しています。

## 開発への支援

steamac Liteは、これからも無料で公開していく予定です。このForkの改良・検証・保守を続けるため、r-fallingstarへの任意の支援を受け付けています。

[GitHub Sponsorsで開発を支援する](https://github.com/sponsors/r-fallingstar)

支援は任意です。個別サポートや機能追加をお約束するものではありません。
