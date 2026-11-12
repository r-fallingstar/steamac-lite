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

1. 起動時の案内で、マイクと「ゲームで使うときだけカメラを起動」を選びます。カメラの自動使用は初期状態でオンです。macOSの確認が出た場合も許可します。許可だけでは撮影を始めません。
2. 設定の「音声」の右にある「カメラ」で、内蔵カメラを選べます。
3. ゲームがカメラを使用すると撮影を始め、使用を終えると停止します。待機中は黒い映像の更新頻度も毎秒1回までに抑えます。
4. プレビューだけ確認する場合は「許可してカメラを使う」を押します。自分の映像と「SteamOSが受け取ったフレーム数」を確認してください。
5. VRChatはご自身で起動してください。camera.3では検証ディスクのVRChatだけProton-RTSPへ切り替えます。Tracking & IKのSelfie Expressionで自動品質調整をオフにし、品質をBalancedへ設定します。「steamac Built-in Camera Test」を選び、動きが反映されるか確認してください。検証中はこの品質設定を使います。
6. ゲーム側でカメラを無効にし、Macのカメラが停止するか確認します。「カメラを止める」では自動使用もオフになります。設定を閉じると手動プレビューを終えますが、ゲームが使用中の自動撮影は続けます。

起動時にカメラ利用者がいなければ撮影しません。映像は保存しません。今回は内蔵カメラのみ、使用中は320 × 240・15 fpsでSteamOSへ送信します。Mac側からの入力は640 × 480で受け、ゲスト内で縮小します。

## 解像度のpx指定

「画面」→「レンダリング解像度（px）」で選択できます。カスタムでは幅と高さを入力できます。
ウインドウの大きさとは別の設定です。変更を適用するには設定画面の再起動操作を使います。

## 検証状況

- 映像データの形式・解像度指定・設定の保存と読み込みの自動チェックは通過。
- 設定画面のカメラタブが画面内に収まることを確認。
- 複製したSteamOSでテスト映像をV4L2のMMAP経由で取得できること、停止後に黒い映像になることを確認。
- M1・8 GBの実機で内蔵カメラの許可とプレビュー、SteamOS受信フレーム数の増加を確認。初回の「プレビューは見えるが受信が0」の症状は、出力サイズを明示した修正版で解消。
- VRChatは候補表示まで確認。標準ProtonではBalancedモードでも「使用中／非対応」で開始できませんでした。camera.3のProton-RTSP切り替え後のゲーム内確認は未完了です。
- Media Foundation単体診断は起動前に失敗したため判断に使っていません。後述のDirectShow診断では、同じProtonとFEXで実際の映像受信まで確認しています。

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
`guest/camera/dshow-camera-test.c`はDirectShowの列挙・フィルターへの接続・映像サンプルの受信を調べる別の診断です。
同じ検証ディスクのProton ExperimentalとFEXを使い、別の一時RootFS・専用の新しいprefixでWindows用診断を実行しました。カメラの列挙・接続と9フレームの受信が成功しています。ゲームのpressure-vessel環境そのものを再現した試験ではないため、VRChat側での確認は引き続き必要です。

番号の修正後、VRChatには候補が出るものの「使用中／非対応」で開始できないとの結果でした。
[WineのV4L2処理](https://github.com/ValveSoftware/wine/blob/5b557605b4e51f0853ec8e0e4f0eb536c669fae3/dlls/qcap/v4l.c#L488-L501)が要求するBGR24へゲスト内で変換するよう変更しています。
色の変換、V4L2のMMAPとread()の両方での取得、形式・解像度・フレーム間隔の指定はテスト映像で確認済みです。
これはLinux側での確認であり、VRChatでのトラッキング成功は別途確認が必要です。

自動撮影は、固定したv4l2loopback版のクライアント利用通知で制御します。
OSのカメラ許可と自動撮影の設定、手動プレビューは別の状態として扱います。
初回の案内後は、更新時に以前の許可が外れた場合だけ再案内します。許可が残っている更新や通常の起動では表示しません。明示的にオフにした自動使用と許可しなかった機能も聞き直しません。

## Balancedモードの確認

標準Protonとproton-rtsp-11.0-20260609-4で、列挙・形式設定・フレームレート関連APIを比較しました。今回調べた結果に差がなく、どちらも映像サンプルを取得できました。比較用ツールは検証ディスクにだけ配置し、VRChatのProton選択は変更していません。

VRChatのログには低フレームレートによるSelfie停止の記録もありました。[公式Wikiの品質表](https://wiki.vrchat.com/wiki/Selfie_Expression#Selfie_Expression_Quality_Level)と実験版の640 × 480・15 fpsが一致していなかったため、ゲスト出力をBalancedの320 × 240・15 fpsへ変更しています。これが「使用中／非対応」の原因だと確定したわけではありません。

## PreviewとRGB32の比較

Balancedでも失敗したため、ゲームを起動せず、実際のSteam Runtimeのpressure-vesselとFEXを使って診断しました。専用prefixとテスト映像を使い、内蔵カメラは開きません。

| 診断 | 標準Proton Experimental | Proton-RTSP -4 |
| --- | --- | --- |
| Capture・形式指定なし | 映像取得成功 | 前の単独診断で成功 |
| 同じデバイスへの2個目のフィルターを保持 | 映像取得成功 | 今回は未実施 |
| Capture・RGB32指定 | 接続失敗 0x80040217 | 今回は未実施 |
| Preview・形式指定なし | 映像取得成功 | 今回は未実施 |
| Preview・RGB24指定 | 230,400バイトの映像取得成功 | 今回は未実施 |
| Preview・RGB32指定 | 接続失敗 0x80040217 | 307,200バイトの映像取得成功 |

これまでのCaptureだけの比較では、Preview側の差を検出できていませんでした。Proton-RTSPには[Smart TeeのPreview用バッファーとRGB32変換の修正](https://github.com/SpookySkeletons/wine/commit/5f187cd7e5e5b9de82376e501a31661c567a409b)があります。今回の差はこの修正と整合しますが、VRChatが失敗した呼び出し自体を確認したわけではありません。

Macの物理カメラはsteamacが開き、VRChatはSteamOS内の仮想カメラを開きます。出力側をsteamacが保持したまま上記診断が成功しているため、その保持だけで必ず競合するわけではありません。2個目のフィルターを保持する診断は、2本のストリームの同時取得を保証するものではありません。

camera.3の起動スクリプトは、検証ディスクのVRChatに限り`proton-rtsp-11.0-20260609-4`を選択します。検証済みアーカイブの印と、qcap.dll・qcap.so・マニフェストのハッシュを照合します。Steam起動前に変更し、元の設定を保存します。他のProtonを利用者が選んでいた場合は置き換えません。通常版は変更しません。

標準Protonへ戻す場合は、実験版を終了してから次で起動できます。後から利用者が変更した選択は保持します。

```sh
python3 scripts/camera/launch-experiment.py --standard-proton
```

診断の再実行は`prepare-dshow-test.py --container`と`test-bridge.py --container`を使います。結果の`container-validation.json`には成功した基準ケースと、失敗した比較ケースを分けて記録します。全形式の対応やVRChatでの成功を示すものではありません。
