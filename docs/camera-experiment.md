# 内蔵カメラ実験版

通常版と分けたローカル検証用です。まだ公開版には含めていません。

## 起動

通常版とDocker Desktopを終了してから、リポジトリで次を実行します。

```sh
python3 scripts/camera/launch-experiment.py
```

起動スクリプトは専用アプリ・複製したSteamOSディスク・別の設定領域を使います。
初回だけ通常版の設定をコピーし、以後の変更は実験版に保存します。
自動更新・統計送信・SSH・VRはこの検証では無効です。

## 確認すること

1. 起動時にマイクの案内が出たら、使う場合は許可します。カメラだけ確認する場合は後回しでも構いません。
2. 設定の「音声」の右にある「カメラ」を開きます。
3. 内蔵カメラを選び、「許可してカメラを使う」を押します。macOSの確認でも許可します。
4. 自分の映像が表示され、「SteamOSが受け取ったフレーム数」が増えるか確認します。
5. VRChatでWebカメラトラッキングを試す場合は、ご自身でVRChatを起動します。Tracking & IKのSelfie Expressionで「steamac Built-in Camera Test」を選べるか、動きが反映されるか確認してください。
6. 「カメラを止める」を押してカメラが停止するか確認します。設定画面を閉じた場合も停止します。

カメラは起動のたびにオフです。映像は保存しません。今回は内蔵カメラのみ、640 × 480・15 fpsで送信します。

## 解像度のpx指定

「画面」→「レンダリング解像度（px）」で選択できます。カスタムでは幅と高さを入力できます。
ウインドウの大きさとは別の設定です。変更を適用するには設定画面の再起動操作を使います。

## 検証状況

- 映像データの形式・解像度指定・設定の保存と読み込みの自動チェックは通過。
- 設定画面のカメラタブが画面内に収まることを確認。
- 複製したSteamOSでテスト映像をV4L2のMMAP経由で取得できること、停止後に黒い映像になることを確認。
- M1・8 GBの実機で内蔵カメラの許可とプレビュー、SteamOS受信フレーム数の増加を確認。初回の「プレビューは見えるが受信が0」の症状は、出力サイズを明示した修正版で解消。
- VRChatのSelfie Expressionは利用者の確認待ち。
- 単体のWindows Media Foundation診断はFEX/Protonの起動条件が整わず実行できていないため、VRChatでの動作可否は未確認。

Linux側は`fx.camera`専用ポートとv4l2loopbackを使います。カーネル設定を一致させてモジュールをビルドし、実際のゲストで読み込めることを確認しています。
ビルド元とハッシュは実験版の`steamac-camera-build.json`に記録します。

## カメラ一覧に出ない場合の調査

初回のVRChatテストではカメラが候補に表示されませんでした。実験版が使っていた
`/dev/video20`は、WineのDirectShow列挙が調べる`/dev/video0`〜`/dev/video9`の範囲外でした。
空いている0〜9の番号を使うよう変更し、使用中のデバイスを置き換えないようにしています。
カメラ名に含まれる空白も、カーネルのモジュール引数として保持するよう修正しました。

根拠は[Wineのカメラ列挙](https://github.com/wine-mirror/wine/blob/7384c8babcaa411a0014bf223068a633d7bfa899/dlls/devenum/createdevenum.c#L714-L763)と
[Linux側のデバイス番号との対応](https://github.com/SpookySkeletons/wine/blob/fd920bd63abb7bf8b52b0f8e40da922ab9e784a4/dlls/avicap32/v4l.c#L69-L118)です。
これは列挙対象に入れる修正であり、VRChatでの映像取得成功を意味しません。

Media Foundation側は[映像デバイス列挙が未実装の経路](https://github.com/ValveSoftware/wine/blob/5b557605b4e51f0853ec8e0e4f0eb536c669fae3/dlls/mf/main.c#L933-L955)があるため、
`MFEnumDeviceSources`の結果だけではDirectShowの動作を判断できません。
`guest/camera/dshow-camera-test.c`はDirectShowの列挙とフィルターへの接続を調べる別の診断です。
コンパイルは通過していますが、ゲームと同じ起動環境での実行は未確認です。
