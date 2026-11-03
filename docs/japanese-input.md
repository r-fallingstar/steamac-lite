# 日本語入力とUS/JIS配列

Lite.7では中国語（ピンイン）と韓国語（2ボル式）も初回に設定します。追加ダウンロードは不要です。初回の表示言語が中国語ならピンイン、韓国語ならHangul、それ以外は従来どおりAnthyを選び、英数入力で始めます。中国語はShift、韓国語はControl＋Spaceで英数と切り替えます。Control＋.で入力方式を変更できます。既存の入力設定は後続の起動でリセットしません。[多言語入力の仕様](cjk-input.md)も参照してください。

Lite v1.9.4-lite.2から、Macが認識している物理キーボードを起動時に判別します。Carbonの`LMGetKbdType`と`KBGetLayoutType`を使い、JISならゲストを`jp`、ANSIなら`us`にします。日本語入力ソースの有無・表示言語は配列判定に使いません。

## 入力方法

初回のモードは直接英数です。テキスト欄を選び、Control＋Spaceで日本語入力を有効にし、ローマ字入力・Spaceで変換・Enterで確定します。JISでは「かな」でひらがな、「英数」で直接英数へ切り替えます。ゲームで移動する際は直接英数へ戻してください。

macOSのATOKや日本語IMEの変換結果を渡す方式ではなく、ゲストのIBus・Anthyが変換します。SteamOSに既存の`ibus`、`ibus-anthy`、`anthy`、`python-gobject`を使います。IMEパッケージのダウンロードやmacOSの入力設定変更は行いません。

通常のX11/Protonアプリ向けにXIMを有効にし、Steam用・ゲーム用の両Xwaylandへ同じIBusを接続します。候補表示にはIBusのGTKパネルを使います。ゲーム独自の入力欄、Proton・Steamの更新によっては追加の対応が必要になることがあります。

JISのキーは、Macの「英数」をLinuxの`KEY_MUHENKAN`、「かな」を`KEY_HIRAGANA`へ送ります。Anthyのショートカットもそのキーへ対応付けます。従来の韓国語キーへの割り当てを修正しています。記号の違いはゲストのXKB配列で解釈します。

## 手動指定と再判別

外付けキーボードを接続・交換したらアプリを再起動してください。macOSが物理配列を誤認している場合やリマップ環境では、終了してから手動指定できます。

```sh
open -a '/Applications/SteamAC Lite.app' --args --keyboard-layout us
open -a '/Applications/SteamAC Lite.app' --args --keyboard-layout jis
```

指定なし、または`--keyboard-layout auto`で自動判別します。1回の起動につき1種類の配列を使用します。異なる配列のキーボードを同時に使い分ける機能はありません。ISOは形状判別と追加キーの対応のみで、国別配列はUSとして扱います。

## 設定の保存

初回だけIBus/Anthyの入力エンジン、直接英数の初期モード、Control＋SpaceとJISキーを設定します。その後のユーザーのショートカット変更は上書きしません。変更前の値はゲストの`~/.config/steamac/japanese-input-v1.json`に保存します。配列自体は毎回ホストから受け取ります。

Desktop ModeのKWinにも`~/.config/kxkbrc`を通して配列を設定します。前回の自動設定からユーザーが変更していた場合は、その設定を優先します。Desktop ModeのWayland入力はゲームモードとは経路が異なり、下記の統合テストの対象外です。

起動パラメーター`steamac.japanese_ime=0`を明示した場合は日本語入力の自動設定・XIM追加を行いません。既存のユーザー設定は残ります。`steamac.keyboard=us|jis|iso`も検証してから扱い、任意のコマンドや配列名は実行しません。

## テスト

```sh
python3 scripts/test/keyboard-setup.py
'/Applications/SteamAC Lite.app/Contents/MacOS/steamac-vm' --selftest-keyboard
python3 scripts/lite/test-input.py --disk /path/to/stopped-test-copy.img --layout jis
python3 scripts/lite/test-input.py --disk /path/to/stopped-test-copy.img --layout us
```

ゲスト統合テストは、IBusの専用入力コンテキストで「nihongo→日本語」を変換し、かな・英数・Control＋Spaceを確認します。実際の2つのXwaylandについて、Shift＋2とPの右のキーの記号が配列どおりであること、XIMサーバーの登録を確認します。ゲームや他のアプリへキー入力せず、SSHも有効にしません。使用中のディスクと両アプリの既定ディスクは拒否します。

2026-11-02にApple M1・RAM 8 GiB・macOS 27.2上でJIS・USの両設定の統合テストが成功しました。このMacの物理配列はJISとして自動検出し、USはCLIで明示したゲスト設定で検証しています。ゲスト表示は`xrandr`で59.96 Hzを確認しました。[確認結果](input-validation.json)を保存しています。VRChat内の日本語入力は、この自動テストでは確認していません。
