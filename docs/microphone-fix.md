# マイク入力の修正

macOSのマイク権限が許可済みでもSteamOSの録音が無音になる問題を修正するlibkrunパッチです。

対象: `host/libkrun/patches/0029-snd-wait-for-capture-start-and-microphone-readiness.patch`

## 原因

- CoreAudioの入力はFloat32ですがコールバック用バッファーのチャンネル数と1フレームのサイズが初期値のままでした。CoreAudioがバッファーを受け付けず音声データを読み取れませんでした。
- マイクの準備が終わる前に無音データで録音バッファーを返していました。実時間より速く録音位置が進むためSteamOS側でXRUNが発生していました。

## 変更

- マイクの起動前にCoreAudioの入力形式をコールバックへ設定します。
- PCM_STARTとマイクの準備がそろうまで録音バッファーを保持します。
- マイクを開けなかった場合はIO_ERRを返します。

マイク権限やmacOSの入力機器は変更しません。Macで選ばれている標準入力を使います。

## ビルド

`host/libkrun/build.sh`はこのパッチを含む全パッチを適用します。
Lite.6以降のアプリ作成には修正版のlibkrunが必要です。Rust 1.90.0を用意してからビルドします。

```sh
bash scripts/lite/build-audio-library.sh
LIBKRUN_OVERRIDE="$PWD/work/out/host/lib/libkrun.1.dylib" \
  bash scripts/lite/build-app.sh
```

`LIBKRUN_OVERRIDE`を省略するとビルドを止めます。修正前のライブラリが混ざるのを防ぎます。

今回の配布版は、SHA-256を固定したLite.5のDMGと修正版libkrunから`scripts/lite/build-audio-update.py`で作成します。ランチャーとゲストレイヤーはLite.5の配布物を引き継ぎます。アプリのバージョンとビルド記録を更新してから署名します。

## 確認

- 音声関連のRustテスト32件が成功。実機操作用の1件は除外。
- M1 MacBook ProでSteamOSのPulseAudio互換APIから8秒間の入力を確認。
- 録音を閉じて再度開いた場合も音声データを確認。
- VRChatの起動と通話の確認は未実施。
