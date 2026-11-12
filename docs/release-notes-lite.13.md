更新後にマイクの許可を確認できるようにしました。

- 初回起動と更新後の初回起動で、許可済みの場合もマイクの確認画面を表示します。SteamOSの起動前にmacOSのマイク許可を確認します。許可が必要な場合は「マイクを許可…」からOSの確認画面を開けます。
- 許可されていない場合はシステム設定への案内を表示します。許可がすでにオンでも更新後に使えなくなった場合は、一度オフにしてからオンにする手順を案内します。
- 「設定 → 音声」に許可の状態と「マイクの設定を開く…」「もう一度確認」を追加しました。設定から戻ると状態を更新します。
- マイクが不要なら、そのままSteamOSを利用できます。案内を閉じた場合は、同じ版で繰り返し表示しません。
- 日本語・英語・韓国語・簡体字中国語・ロシア語に対応しました。導入ガイドも4言語で更新しました。

この版もad-hoc署名です。更新をまたぐマイク許可の継続は保証されず、再び許可が必要になる場合があります。正式なDeveloper ID署名への移行は含みません。報告されたすべてのマイク不具合の解消を確認したものではありません。

アプリ内の「アップデートを確認…」から更新できます。BOOTHのネットインストーラーもこの版を取得します。SteamOSのディスクと設定は保持します。

---

Microphone access can now be checked after an app update.

- On the first launch and the first launch after each update, the app shows a microphone check even if access is already allowed. It checks macOS authorization before starting SteamOS. Choose **Allow Microphone…** when offered to open the OS permission dialog.
- If access is denied or restricted, the app explains how to open Microphone settings. It also suggests turning this app’s permission off and on again if the microphone stopped working after an update.
- **Settings → Sound** now shows access status, **Open Microphone Settings…**, and **Check Again**. Status refreshes when returning to the app.
- SteamOS can be used without a microphone. Choose Later to continue without requesting access now. Dismissing the notice prevents repeated startup notices for that version. macOS decides whether its own permission dialog is shown; the app does not reset permissions to force it.
- The new controls support all five app languages. The setup guide has been updated in all four guide languages.

This build is still ad-hoc signed. Microphone permission may need to be granted again after updates; this release does not add Developer ID signing or confirm that every reported microphone problem is resolved.

Existing users can update through **Check for Updates…**. The BOOTH online installer also downloads this version. SteamOS disks and settings are kept.
