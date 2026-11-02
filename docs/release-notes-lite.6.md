# SteamAC Lite 1.9.4-lite.6

マイク権限が許可済みでもSteamOSの録音が無音になる問題を修正しました。

## ダウンロード

Assetsの **SteamAC-Lite-1.9.4-lite.6-macos-arm64.dmg** をダウンロードしてください。DMGを開いてSteamAC Lite.appをApplicationsへコピーします。更新する場合はSteamAC Liteを終了してから置き換えてください。既存のSteamOSディスクとゲームデータはそのまま使えます。

## 修正内容

- Macから音声を受け取るバッファーのチャンネル数とサイズを正しく設定しました。
- マイクの準備前に無音データを返し続ける処理を修正しました。
- マイクを開けなかった場合は録音エラーを返すようにしました。

初回の言語選択、日本語入力、US/JIS配列の判別、60 Hz表示、スペックに応じた設定、VRChat向け設定はLite.5から引き継いでいます。

## 確認したこと

- 修正コードを使ったアプリでM1 MacBook Pro・RAM 8 GBの内蔵マイク入力を確認。
- SteamOSのPulseAudio互換APIで8秒間の録音を2回確認。ALSAのモノラル録音も確認。
- 配布用のlibkrunは同じ修正コードから再ビルド。音声テスト32件が成功。
- DMGからコピーしたアプリの署名とメモリ配分・配列判別・言語・翻訳のチェックを実施。

VRChat内の通話と外付けマイクは未確認です。録音テストの音声データは保存していません。

[写真付き導入ガイド](https://r-fallingstar.github.io/steamac-lite/) · [修正の詳細](https://github.com/r-fallingstar/steamac-lite/blob/main/docs/microphone-fix.md)

Apple Silicon・macOS 15.5以降向けの実験版です。ad-hoc署名でAppleの公証は受けていません。
