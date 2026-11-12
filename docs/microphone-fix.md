# マイク入力の修正

## Lite.13: 更新後のマイク許可

Lite.9〜12には下記の録音処理の修正が含まれています。一方、ad-hoc署名では更新ごとにアプリの署名要件が変わるため、以前のマイク許可が継続しない場合があります。このMacでも、Lite.12に対するTCCの事前確認で以前の署名要件との不一致が記録されました。システム設定の許可スイッチはオンのままでした。報告者の環境で同じ原因かは未確定です。

Lite.13は公開APIでマイクの許可を確認します。未確認ならユーザー操作でOSの許可画面を開き、拒否・制限時はシステム設定へ案内します。「設定 → 音声」でも状態を確認できます。起動時の確認が終わるまでVMを起動せず、OSの確認待ちでゲストの録音要求がタイムアウトすることを避けます。マイクを使わず続行することもできます。許可を自動変更したり、TCCをリセットしたりはしません。

正式なDeveloper ID署名への移行は含みません。更新をまたぐ許可の継続は保証されず、再許可が必要になる場合があります。

参考: [Apple: コード署名とマイク許可の同一性](https://developer.apple.com/documentation/technotes/tn3127-inside-code-signing-requirements)、[macOSのメディア取得の許可](https://developer.apple.com/documentation/bundleresources/requesting-authorization-for-media-capture-on-macos)。

## Lite.6: 録音処理

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
