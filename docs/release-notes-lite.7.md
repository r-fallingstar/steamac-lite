# SteamAC Lite 1.9.4-lite.7

## 日本語

- 本体のメニュー・設定・初期設定画面に韓国語を追加しました。対応言語は日本語・英語・韓国語・簡体字中国語・ロシア語です。
- 中国語（ピンイン）と韓国語（2ボル式）を初回に設定します。SteamOS付属のエンジンとフォントを使うため追加ダウンロードは不要です。
- 初回は表示言語に合う入力方式を選び、英数入力で始めます。中国語はShift、韓国語と日本語はControl＋Spaceで英数入力と切り替えます。Control＋.で入力方式を変更できます。
- 新しいSteamOSディスクではSteamも韓国語で始められます。既存のSteamの言語は保持します。
- 日本語入力・US/JIS自動判別・60 Hz・Lite.6のマイク修正を含みます。

JIS・USの両設定で「日本語」「你好」「한글」の変換、英数への切り替え、入力設定の保持、Steam用とゲーム用の両XwaylandへのXIM登録を確認しました。VRChat内のチャット欄での入力は今回の自動テストに含みません。VRChatはテスト中に起動していません。

韓国語訳と入力説明はGemini 3.8 Flash Highで校閲し、書式引数・改行・訳抜けを別途検査しました。

## English

- Added Korean menus, settings, dialogs and first-run language selection.
- Initial setup enables the existing SteamOS Japanese, Chinese Pinyin and Korean 2-set engines. No extra input-engine or font downloads are needed.
- Chinese and Korean display languages select the corresponding initial input method, starting in Latin mode. Shift toggles Chinese; Control+Space toggles Korean and Japanese. Control+period changes input methods.
- New SteamOS disks can start Steam in Korean. Existing Steam language settings are retained.
- Includes physical US/JIS detection, 60 Hz defaults and the Lite.6 microphone fix.

Input conversion and settings retention were checked with JIS and US guest layouts and both Xwayland servers. VRChat-specific text fields were not tested. This remains an experimental Apple Silicon build, signed ad hoc and not notarized.
