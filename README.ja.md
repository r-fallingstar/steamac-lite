# SteamAC Lite

[English](README.md) · **日本語**

Apple Silicon・RAM 8 GBのMac向けに、[StonkGuy/steamac](https://github.com/StonkGuy/steamac)の`v1.9.4-eac.1`から作成した実験版です。Mac上の仮想マシンでSteamOSを動かし、FEX・Proton・DXMTを利用します。

**[アプリをダウンロード（M1以降のMac用DMG）](https://github.com/r-fallingstar/steamac-lite/releases/download/v1.9.4-lite.3/SteamAC-Lite-1.9.4-lite.3-macos-arm64.dmg)**

DMGを開いて **SteamAC Lite.app** を **Applications** へコピーするだけでアプリを導入できます。ビルドは不要です。[はじめての導入手順](docs/quick-start.ja.md) · [Releaseと更新内容](https://github.com/r-fallingstar/steamac-lite/releases/tag/v1.9.4-lite.3)

macOS 15.5以降・Apple Silicon向けです。この実験版はApple未公証で、初回起動時の案内は導入手順に記載しています。SteamOS・ゲームは別途ダウンロードし、VRChat用のFEX・Proton設定は現時点で手動です。

## このForkの変更

| 項目 | Liteの既定値・動作 |
|---|---|
| VMのRAM | Macに応じて3〜16 GiB。8 GBでは3 GiB |
| ゲスト用ディスクスワップ | 8 GB向け設定では`/home`のext4上に4 GiB。既存のzramは維持 |
| 初期描画 | MacのRAMと画面に合わせて960×600〜1920×1200。Retinaなし、60 Hz |
| 手動設定 | 設定画面で自動・軽量・手動を選択。個別に選んだ値を優先 |
| 表示言語 | 初回起動で選択。日本語の設定・メニュー・初期設定案内に対応 |
| 描画経路 | DXMTを優先。利用できなければVulkan |
| キーボード | Macの物理配列から起動時にUS/JISを自動判別 |
| 日本語入力 | SteamOS付属のIBus・Anthy。追加ダウンロード不要 |
| アプリ・設定 | `SteamAC Lite.app`として通常版と別に保存 |

macOSの仮想メモリ設定は変更しません。スワップはRAM不足による終了を減らすための補助で、物理RAMやGPUメモリを増やすものではありません。頻繁なスワップは遅くなります。**60 Hzは画面更新の設定であり、ゲーム内60 fpsの保証ではありません。**

[Mac別の自動設定表と設定方法](docs/performance-profiles.md)

初回に「日本語」を選ぶと、ランチャーの設定画面やメニューを日本語で表示します。あとから **設定… > 一般 > 表示言語** で変更でき、アプリの再起動で反映されます。SteamOS・Steam・ゲーム自体の表示言語は、それぞれの設定を使います。

## 日本語の入力

1. テキスト欄を選びます。初回は英数入力で始まります。
2. **Control＋Space**で英数・日本語を切り替えます。JISでは**かな**でひらがな、**英数**で直接入力へ切り替えられます。
3. ローマ字で入力し、**Space**で漢字変換、**Enter**で確定します。

配列はmacOSの表示言語やATOK等の入力ソースから推測せず、物理キーボード情報を使います。外付けキーボードを変更した場合はアプリを再起動してください。ISOの形状も判別しますが、地域別の英独仏配列までは自動推定しません。複数配列の同時利用や特殊なリマップ環境には制限があります。

詳しい設定と手動指定は[日本語入力と配列](docs/japanese-input.md)にあります。

## ビルドと起動

導入済みの`FX Steam Launcher.app` 1.9.4-eac.1、Swift 6、SDK、Git、Python 3、erofs-utilsが必要です。

```sh
python3 scripts/test/low-memory-swap.py
python3 scripts/test/keyboard-setup.py
bash scripts/lite/build-app.sh
```

出力は`work/out/SteamAC Lite.app`です。元の署名付きアプリのカーネル・グラフィックス等を再利用し、変更したランチャーとゲスト設定を組み込みます。全コンポーネントをソースから構築するリリース手順とは異なります。

停止済みのSteamOSディスクのコピーで試してください。同じディスクを複数のVMから同時に開かないでください。初回のスワップ作成時には、Mac・ゲストにそれぞれ8 GiB以上の空き容量が必要です。VRChatを使う場合はProton ExperimentalとProton EasyAntiCheat Runtime、対応するFEXの設定が別途必要です。

[ビルド手順とメモリ配分の詳細](docs/8gb-profile.md) · [上流のゲーム設定](SETUP.md)

## 動作確認の範囲

Apple M1・RAM 8 GiB・macOS 27.2で、Steamの画面表示と正常終了、3 GiBのVM RAM、4 GiBのゲスト用スワップを確認しました。ユーザーからVRChatが動作したとの報告もあります。FPSや長時間の安定性、すべてのワールド・アバターの互換性は未確認です。

配列・日本語入力の確認方法は[日本語入力と配列](docs/japanese-input.md)を参照してください。上流版の最低RAM要件は16 GBで、この8 GBプロファイルは独自の実験です。Valve、VRChat、Epic Games、FX GAMES等の公式製品ではありません。元のライセンス・noticeは保持しています。
