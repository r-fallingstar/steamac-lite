# steamac Lite v1.9.8-lite.9

## 日本語

任意の診断送信を有効にしている場合、macOSがVMプロセスを `SIGKILL` で終了したとき、非公開の診断Issueに `kill_reason` が入るようになりました。`memory` はカーネルがメモリ管理による終了を示した場合です。コード署名と復号のエラーも区別します。理由が指定されていない場合は `unspecified`、終了情報を取得できなかった場合は `unavailable` と記録します。この2つからはメモリ圧迫の有無を判断できません。

送信する理由は固定の分類です。診断送信は任意で、設定の「一般」から切り替えられます。既存のSteamOSディスクと設定を引き継ぎます。

### 初回画面が出ない場合

アプリが止まっている間に、[起動時のログ採取手順](https://github.com/r-fallingstar/steamac-lite/blob/main/docs/startup-hang-investigation.md#lite8以降で初回画面が出ない場合)に沿って、Mac内の起動段階とプロセスのサンプルを確認できます。このリリースにも [採取スクリプト](https://github.com/r-fallingstar/steamac-lite/releases/download/v1.9.8-lite.9/collect-startup.sh) を添付しています。

## English

For opted-in diagnostics, a VM `SIGKILL` report now includes a fixed `kill_reason` category in the private issue. `memory` means the macOS kernel recorded a memory-management termination. Code-signing and decryption failures have their own categories. `unspecified` and `unavailable` leave the role of memory pressure undetermined. Existing settings and SteamOS disks are retained.
