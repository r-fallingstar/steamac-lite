# SteamAC Lite

[English](README.md) · **日本語**

**[写真付きの導入ガイド](https://r-fallingstar.github.io/steamac-lite/)** — ダウンロードからVRChat向け設定まで、実画面で案内します。

[日本語](https://r-fallingstar.github.io/steamac-lite/?lang=ja) · [English](https://r-fallingstar.github.io/steamac-lite/en/) · [한국어](https://r-fallingstar.github.io/steamac-lite/ko/) · [简体中文](https://r-fallingstar.github.io/steamac-lite/zh-CN/)

Apple Silicon・RAM 8 GBのMac向けに、[StonkGuy/steamac](https://github.com/StonkGuy/steamac)の`v1.9.4-eac.1`から作成した実験版です。Mac上の仮想マシンでSteamOSを動かし、FEX・Proton・DXMTを利用します。

**[アプリをダウンロード（M1以降のMac用DMG）](https://github.com/r-fallingstar/steamac-lite/releases/download/v1.9.4-lite.8/SteamAC-Lite-1.9.4-lite.8-macos-arm64.dmg)**

Lite.6でSteamOSのマイク入力が無音になる問題を修正しました。[原因と確認内容](docs/microphone-fix.md)。

DMGを開いて **SteamAC Lite.app** を **Applications** へコピーするだけでアプリを導入できます。ビルドは不要です。[はじめての導入手順](docs/quick-start.ja.md) · [Releaseと更新内容](https://github.com/r-fallingstar/steamac-lite/releases/tag/v1.9.4-lite.8)

macOS 15.5以降・Apple Silicon向けです。この実験版はApple未公証で、初回起動時の案内は導入手順に記載しています。SteamOS・ゲームは別途ダウンロードします。初回の「VRChat向け設定」で、FEXの導入・Protonの選択・起動オプションを自動で設定できます。Steamへのログインと、Steamに表示されるダウンロード確認は本人が操作します。[設定の流れ](docs/vrchat-setup.ja.md)を参照してください。

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

導入済みの`FX Steam Launcher.app` 1.9.4-eac.1、Swift 6、SDK、Git、Python 3、erofs-utilsが必要です。

```sh
python3 scripts/test/low-memory-swap.py
python3 scripts/test/keyboard-setup.py
bash scripts/lite/build-app.sh
```

出力は`work/out/SteamAC Lite.app`です。元の署名付きアプリのカーネル・グラフィックス等を再利用し、変更したランチャーとゲスト設定を組み込みます。全コンポーネントをソースから構築するリリース手順とは異なります。

停止済みのSteamOSディスクのコピーで試してください。同じディスクを複数のVMから同時に開かないでください。初回のスワップ作成時には、Mac・ゲストにそれぞれ8 GiB以上の空き容量が必要です。「VRChat向け設定」は既定で有効です。Steamへのログイン後、必要なツールのダウンロードが終わると追加設定を適用し、Steamを一度再起動します。VRChatは自動では起動しません。

[ビルド手順とメモリ配分の詳細](docs/8gb-profile.md) · [上流のゲーム設定](SETUP.md)

## 動作確認の範囲

Apple M1・RAM 8 GiB・macOS 27.2で、Steamの画面表示と正常終了、3 GiBのVM RAM、4 GiBのゲスト用スワップを確認しました。作者の同環境でVRChatの動作も確認しました。FPSや長時間の安定性、すべてのワールド・アバターの互換性は未確認です。

Lite.5では、新しいSteamOSディスクの作成から、FEX・Proton・EACのダウンロード、VRChat向け設定の完了まで確認しました。Steamへのログインとインストール確認は手動です。別の未起動SteamOSディスクで、Steamの初回ログイン画面が日本語になることも確認しています。[検証結果と制限](docs/validation-lite.5.md)を参照してください。

配列・日本語入力の確認方法は[日本語入力と配列](docs/japanese-input.md)を参照してください。上流版の最低RAM要件は16 GBで、この8 GBプロファイルは独自の実験です。Valve、VRChat、Epic Games、FX GAMES等の公式製品ではありません。元のライセンス・noticeは保持しています。
