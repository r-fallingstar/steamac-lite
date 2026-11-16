# steamac Lite v1.9.8-lite.7

## 日本語

初回起動ウィザードで、表示言語・マイク・カメラ・任意の診断情報送信をまとめて選べるようにしました。GitHubのDMGと、BOOTHのネットインストーラーが取得する本体は同じです。

マイク・カメラは「続ける」のあと、選択したものが未確認の場合にだけmacOS標準の許可画面を出します。許可の取得だけでは撮影・録音を始めません。拒否済みの権限やmacOSの許可の解除は、ウィザード内の設定ボタンから変更できます。従来の通知ダイアログへ多数の項目を載せる構成をやめ、通常のウィンドウで先に内容を表示する形にしました。検証中に見つかった説明文の重なりも修正しました。

Lite版の「クラッシュレポートと診断を送信」は、上流のSentryから作者の非公開GitHubに送信先を変更しました。既定はオフです。以前の設定がオンでも同意を自動移行せず、初回ウィザードであらためて選びます。解除は「設定 → 一般」で行え、以後の自動送信を止めて未送信分を削除します。

有効にした場合は、起動が3分間進まない、起動後のアプリが応答しない、異常終了などの情報を送ります。操作待ちやスリープ後の猶予を設けています。自動報告の内容は、アプリ・macOSの版、Macの型番・チップ・メモリ、固定の起動段階、経過時間、終了コードやシグナルです。名前、アカウント、画面、ファイル内容、環境変数、パス、ログ全文は自動送信しません。端末を継続識別するIDも使いません。

「問題を報告」も同じ非公開の送信先に統一しました。メールは任意で、説明と選択したランチャーログの抜粋をプレビューして送れます。自動送信をオンにする必要はありません。

報告はCloudflareの中継サーバーで受信して非公開GitHubへ同期します。GitHubへは1時間ごとにまとめて同期し（必要な場合は作者が手動で実行）、反映が遅れる場合もあります。表示される報告IDは中継側の受信確認です。受信済みの報告は、ローカルの設定をオフにしても削除されません。OSが監視用ランチャー自体を実行させない場合や、初回の同意画面に到達できない場合は検出できません。ネイティブクラッシュのスタック全文は自動収集しません。

手元のMacで、ウィザードの表示・操作、日英の配置検証、486項目の診断・許可選択テスト、異常終了と通常終了、旧版からの更新処理、Macの送信処理から非公開GitHubへの到着を確認しました。既存のSteamOSディスク・ゲーム・設定を引き継ぎます。M3で報告された起動停止の原因が確定した、または修正できたという更新ではありません。

## English

The first-run wizard now combines language selection, microphone/camera access and optional diagnostics. The GitHub DMG and the app downloaded by the BOOTH online installer use the same wizard.

Selected, undecided microphone/camera permissions are requested from macOS after Continue. Permission requests alone do not start capture. Privacy settings buttons cover access previously denied or permission revocation. The wizard is an ordinary window that paints its contents before requesting access; the overlapping text found during testing was corrected.

Lite's crash/diagnostic reporting now goes to the author's private GitHub instead of upstream Sentry. It is off by default. Previous recipient consent is not migrated. Choose in the wizard and turn off in Settings > General; opting out stops subsequent automatic sends and deletes the local queue.

Opt-in reporting covers startup without progress for 3 minutes, an unresponsive app, and abnormal exits. User dialogs and sleep-related scheduling gaps have grace periods. Automatic records contain app/macOS versions, Mac model/chip/RAM, a fixed startup stage, elapsed time, and available exit codes/signals. Names, accounts, screens, file contents, environment variables, paths and full logs are not automatically sent. There is no persistent device ID.

Report a Problem uses the same private destination. Email is optional; preview the description and selected launcher log excerpt before explicitly sending. This does not enable automatic reporting.

A Cloudflare relay accepts reports and synchronizes them to private GitHub Issues. Reports are synchronized to GitHub hourly to reduce idle job executions; the author can also trigger an import manually. GitHub may delay scheduled jobs. The displayed ID confirms intake acceptance. Opting out does not retract previously received reports. Detection cannot cover macOS blocking the monitoring executable itself or failure before initial consent. Full native crash stacks are not automatically collected.

Checks covered the wizard's display/interaction, Japanese/English layout, 486 diagnostic and permission-selection assertions, abnormal and requested exits, legacy updates, and delivery from native macOS URLSession to private GitHub. Existing disks, games and settings are retained. This release does not establish the cause or resolution of the reported M3 startup hang.
