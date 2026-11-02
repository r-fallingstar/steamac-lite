# SteamAC Lite: experimental 8 GB profile

Apple Silicon・RAM 8 GB向けの試作です。**VRChatが快適に動作する、重いワールドを利用できる、という保証はありません。** 上流の最低要件は16 GBです。

## 変更内容

| 項目 | 上流の8 GB Macでの自動設定 | Liteの初期設定 |
|---|---|---|
| VM RAM | 4 GiB | 3 GiB |
| GPUの報告予算 | 1 GiB | 2 GiB |
| macOS・ドライバの予算 | 3 GiB | 3 GiB |
| 初期描画 | 1280×800、60 Hz | 960×600、30 Hz、Retinaなし |
| 追加ディスクスワップ | なし | ゲストのext4 `/home` に4 GiB |
| 描画経路 | 設定による | DXMTを優先、利用できなければVulkan |

GPU予算は報告値で、物理RAMを予約・保証する機構ではありません。解像度の値は初期ウインドウ時の値です。ウインドウサイズを変えると描画サイズも変わります。30 Hzは表示更新頻度であり、ゲームが30 fpsを出すという意味ではありません。

ゲストの匿名メモリをSSDへ退避することで、RAM不足による終了を減らせる可能性があります。ディスクスワップは物理RAMやGPUメモリの代わりにはならず、頻繁なページ入れ替えでは大きく遅くなります。macOSのスワップ設定や上限は変更しません。既存のzram・スワップも置き換えません。

Steam UIのソフトウェア描画と、起動150秒後のページキャッシュ解放は上流に既にある機能を利用します。継続的な`drop_caches`、メモリ容量の偽装、強制的なovercommit、アンチチートの変更は追加していません。

## 起動と戻し方

`SteamAC Lite.app`は別のbundle ID・設定領域・ログ領域を使います。上流アプリを上書きしません。試すときは停止したSteamOSディスクをAPFS cloneして、コピーしたディスクを指定してください。ディスクの同時利用は避けてください。

起動時に軽量プロファイルが既定で有効になります。`--no-low-memory`を付けると、その起動では無効です。通常版のビルドでも`--low-memory`を指定して試せます。`--mem`、`--cpus`、`--display`、`--render-scale`、`--refresh`、描画経路の明示的な引数を優先します。Retinaは軽量プロファイルでは無効です。

追加スワップは`steamac.low_memory=1`の起動だけで有効になります。ファイルは`/home/.steamac-low-memory/swapfile`で、初回に4 GiBを実際に割り当てます。ゲストとMacのディスクには、それぞれ最低8 GiBの空きが必要です。既に作成済みのファイルをゲストで再利用する場合は追加割り当てしません。ext4以外、空き不足、所有者や権限が不適切な既存ファイルの場合は作成を中止し、ログへ理由を出します。作成失敗でもSteam起動を強制停止する構成にはしていません。

通常版へ戻すと追加スワップは自動で有効になりません。ファイルの4 GiB分はコピーしたゲストディスクに残ります。必要ならゲストを停止して、その試作用ディスク全体を削除できます。元のディスクには影響しません。

## ビルド

基点は`StonkGuy/steamac`の`v1.9.4-eac.1`、commit `c5437da7a4fdef5bd0b79546eab4a2a8a6689546`です。

このMac用の開発ビルドでは、元の署名付きアプリから未変更のカーネル・DXMT・Mesa・libkrun等を再利用し、変更したSwiftランチャーをコンパイルして、ゲストレイヤーへスワップサービスを追加します。全コンポーネントをソースから再ビルドする上流のリリース手順とは異なります。元のライセンスとnoticeを保持し、変更したレイヤーには別のprovenanceを保存します。

必要なもの: macOS用Swift 6、SDK、Git、Python 3、erofs-utils（`fsck.erofs`と`mkfs.erofs`）、導入済みのFX Steam Launcher 1.9.4-eac.1。初回はSwiftPM依存関係とlibkrunヘッダー用ソースをダウンロードします。

```sh
python3 scripts/test/low-memory-swap.py
bash scripts/lite/build-app.sh
```

`BASE_APP`、`DEVELOPER_DIR`、`SDK`、`JOBS`、`FSCK_EROFS`、`MKFS_EROFS`を指定できます。標準のCommand Line Tools SDK 26.5があれば使用します。新しいSDKでSwiftUIマクロのプラグインが必要な場合は、対応するXcode一式が必要です。

## 確認する範囲

`--selftest-low-memory`はメモリ配分、無効化、CLIの優先順位をVMなしで確認します。Pythonテストはスワップ作成・再利用、容量不足、非対応ファイルシステム、リンク拒否、失敗時の処理を模擬環境で確認します。

2026-11-02にApple M1・RAM 8 GiB・macOS 27.2で、コピーした既存のSteamOSディスクを使って確認しました。`scripts/lite/smoke-test.py`によるheadless起動で、VM 3 GiB、GPU報告予算2 GiB、追加ディスクスワップ4 GiBの有効化、`Steam is ready`、正常シャットダウンを確認済みです。音声・SSH・VRはこのテストでは無効です。テストは既存のスワップファイルを再利用する実経路も通っています。初回のファイル割り当て・`mkswap`は、情報表示オプションの互換性エラーを修正する前の試行で完了していました。

**Steam起動とVRChatのゲーム内動作確認は別です。** VRChatは他PCでの利用を継続するユーザーの意向に合わせて起動していません。EAC成功・ワールド入室・メモリ圧迫・フレーム時間・長時間安定性は未確認です。音声とGUI操作も、この軽量版の実機テスト対象には含めていません。

```sh
python3 scripts/lite/smoke-test.py --disk /path/to/stopped-test-copy.img
```

テストは指定したコピー上でVMを起動して、終了時に正常シャットダウンを要求します。元アプリの既定のディスクや、使用中のディスクは拒否します。結果とコンソールログはGit管理外の`work/`に保存されます。
