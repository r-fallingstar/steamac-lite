# SteamAC Lite 1.9.4-lite.8

## 日本語

- 初回の入力方式をMacで現在選んでいる入力ソースから判別するようにしました。アプリの表示言語とは連動しません。
- ABC／USなら直接英数入力、対応する日本語・簡体字ピンイン・韓国語2ボル式なら対応する入力方式を用意します。各方式は英数モードで始まります。
- US／JISの物理配列は別に判別します。韓国語UIでもUS配列と英数入力を使えます。
- 判別できない入力ソースや未対応の注音・五筆・3ボル式を、別の入力方式に置き換えません。その場合は直接英数入力で始まります。
- 設定済みのSteamOSの入力設定は保持します。初回だけの判別で、起動後にMacと入力方式を同期する機能ではありません。

日本語・中国語・韓国語の入力方式はControl＋.で選べます。日本語と韓国語はControl＋Space、中国語はShiftで英数入力と切り替えます。これまでの60 Hz設定とマイク修正も含みます。

入力ソース判別、表示言語との独立性、US／JIS配列、3言語の変換と既存設定の保持を確認しました。VRChat内のチャット欄は今回の検証に含みません。VRChatは検証中に起動していません。説明文はGemini 3.8 Flash Highで校閲しました。

## English

- First setup now detects the current Mac input source instead of choosing an input method from the app language.
- ABC/US uses direct Latin input. Supported Japanese, Simplified Chinese Pinyin and Korean 2-set sources select the matching engine, starting in Latin mode.
- Physical US/JIS detection remains separate. For example, Korean menus can be used with a US keyboard and direct Latin input.
- Unknown or unsupported methods, including Zhuyin, Wubi and Korean 3-set, use direct Latin input instead of being replaced with another method.
- Existing SteamOS input settings are kept. Detection runs for initial setup; it does not continuously synchronize input methods with the Mac.

Control+period chooses an input method. Control+Space toggles Japanese and Korean; Shift toggles Chinese. The 60 Hz defaults and microphone fix are included. This experimental build is signed ad hoc and is not notarized.
