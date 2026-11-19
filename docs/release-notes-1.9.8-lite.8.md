# steamac Lite v1.9.8-lite.8

## 日本語

- アプリ内で強制終了したときや、理由を表示して起動を中止したときに、自動で異常終了を報告する問題を修正しました。
- VMが異常終了した場合は、最後の起動段階とVM起動からの経過時間を記録します。プロセスの終了コードとmacOSのシグナルを区別し、同じ終了の重複報告を防ぎます。
- 初回設定の画面が出ない場合に備えて、ランチャーの開始、設定読み込み、画面の生成・表示の段階をmacOSのログに記録します。この記録はMac上に残り、初回の同意前に診断を自動送信することはありません。

### 初回画面が出ない場合

1. 配布ファイルの [collect-startup.sh](https://github.com/r-fallingstar/steamac-lite/releases/download/v1.9.8-lite.8/collect-startup.sh) をダウンロードします。
2. アプリが止まった状態で、ターミナルに下記を入力します。スクリプトの保存先が異なる場合はパスを置き換えてください。

   ```sh
   /bin/zsh ~/Downloads/collect-startup.sh '/Applications/SteamAC Lite.app'
   ```

3. デスクトップに作成されたフォルダの `bootstrap-stages.txt`、`processes.txt`、`sample-*.txt`、`launch-policy.txt` を確認し、必要な箇所をお問い合わせに添えてください。採取できなかった場合はファイル内のエラーも手がかりになります。収集結果はローカルに保存されます。共有前に個人情報が含まれていないか確認してください。

macOSがランチャーを実行する前に止まった場合は、起動段階が記録されないことがあります。プロセスのサンプルやmacOSの起動関連ログを同時に集めることで、切り分けを進められます。M3で報告された起動停止の原因は調査中です。

GitHubのDMGとBOOTHネットインストーラーは同じ本体を配信します。既存のSteamOSディスクと設定は引き継ぎます。

## English

- Automatic diagnostics now skip in-app force quits and startup refusals already explained by the app. A VM failure records the last startup stage, time since VM process launch, and the exit code or signal. A single VM exit produces at most one exit report.
- Before the first-run consent screen, the launcher records fixed startup milestones in the local macOS log. There is no automatic diagnostic upload before consent.
- If the first window never appears, download [collect-startup.sh](https://github.com/r-fallingstar/steamac-lite/releases/download/v1.9.8-lite.8/collect-startup.sh) and run `/bin/zsh ~/Downloads/collect-startup.sh '/Applications/SteamAC Lite.app'` in Terminal while the app is unresponsive. Review the resulting Desktop folder before sharing. The process samples and macOS logs can help even when there are no startup milestones. The cause of the reported M3 launch hang is still under investigation.
- The GitHub DMG and the BOOTH online installer deliver the same app. Existing SteamOS disks and settings are retained.
