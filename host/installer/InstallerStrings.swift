import Foundation

enum InstallerLanguage: String, CaseIterable {
    case ja, en, ko, zh = "zh-Hans", ru
    var title: String { [Self.ja:"日本語", .en:"English", .ko:"한국어", .zh:"简体中文", .ru:"Русский"][self]! }
    static var preferred: Self {
        for value in Locale.preferredLanguages {
            for language in Self.allCases where value.hasPrefix(language == .zh ? "zh" : language.rawValue) { return language }
        }
        return .en
    }
}

enum InstallerText: String, CaseIterable {
    case title, introduction, checking, available, destination, choose, install, downloading, verifying, installing
    case completed, current, open, close, cancel, retry, manual
    case networkError, releaseError, verificationError, destinationError, runningError, installError, cancelled
    // Each row is Japanese, English, Korean, Simplified Chinese, Russian.
    static let values: [Self: [String]] = [
        .title: ["SteamAC Liteのインストール", "Install SteamAC Lite", "SteamAC Lite 설치", "安装 SteamAC Lite", "Установка SteamAC Lite"],
        .introduction: ["GitHubから最新版を取得してインストールします。既存のSteamOSディスクと設定は引き継ぎます。", "Download and install the latest version from GitHub. Your existing SteamOS disk and settings are kept.", "GitHub에서 최신 버전을 다운로드하여 설치합니다. 기존 SteamOS 디스크와 설정은 유지됩니다.", "从 GitHub 下载并安装最新版本。已有的 SteamOS 磁盘和设置会保留。", "Загрузите и установите последнюю версию с GitHub. Диск SteamOS и настройки сохранятся."],
        .checking: ["最新版を確認中…", "Checking the latest version…", "최신 버전 확인 중…", "正在检查最新版本…", "Проверка последней версии…"],
        .available: ["%@をインストールできます", "%@ is ready to install", "%@ 버전을 설치할 수 있습니다", "可安装 %@", "Доступна версия %@"],
        .destination: ["インストール先", "Install location", "설치 위치", "安装位置", "Папка установки"],
        .choose: ["変更…", "Change…", "변경…", "更改…", "Изменить…"],
        .install: ["インストール", "Install", "설치", "安装", "Установить"],
        .downloading: ["ダウンロード中…", "Downloading…", "다운로드 중…", "正在下载…", "Загрузка…"],
        .verifying: ["ダウンロードを検証中…", "Verifying the download…", "다운로드 검증 중…", "正在验证下载…", "Проверка загрузки…"],
        .installing: ["インストール中…", "Installing…", "설치 중…", "正在安装…", "Установка…"],
        .completed: ["%@をインストールしました", "%@ is installed", "%@ 버전을 설치했습니다", "已安装 %@", "Установлена версия %@"],
        .current: ["%@がインストールされています", "%@ is already installed", "%@ 버전이 이미 설치되어 있습니다", "已安装 %@，无需重复安装", "Версия %@ уже установлена"],
        .open: ["SteamAC Liteを開く", "Open SteamAC Lite", "SteamAC Lite 열기", "打开 SteamAC Lite", "Открыть SteamAC Lite"],
        .close: ["閉じる", "Close", "닫기", "关闭", "Закрыть"],
        .cancel: ["キャンセル", "Cancel", "취소", "取消", "Отмена"],
        .retry: ["もう一度確認", "Check again", "다시 확인", "重新检查", "Проверить снова"],
        .manual: ["手動ダウンロード", "Download manually", "수동 다운로드", "手动下载", "Скачать вручную"],
        .networkError: ["接続できませんでした。接続を確認してもう一度試すか、手動でダウンロードしてください。", "Could not connect. Check your connection and try again, or download manually.", "연결할 수 없습니다. 연결을 확인한 후 다시 시도하거나 수동으로 다운로드하십시오.", "无法连接。请检查网络后重试，或手动下载。", "Не удалось подключиться. Проверьте соединение и повторите попытку или скачайте приложение вручную."],
        .releaseError: ["インストールできる最新版が見つかりません。Releaseページから手動でダウンロードしてください。", "No installable release was found. Download the app from the releases page.", "설치할 수 있는 최신 버전을 찾을 수 없습니다. 릴리스 페이지에서 수동으로 다운로드하십시오.", "未找到可安装的最新版本。请从发布页面手动下载。", "Не найдена версия для установки. Скачайте приложение со страницы выпусков."],
        .verificationError: ["ダウンロードを検証できませんでした。アプリは変更していません。もう一度試してください。", "The download could not be verified. Your app has not been changed. Try again.", "다운로드를 검증할 수 없습니다. 앱은 변경되지 않았습니다. 다시 시도하십시오.", "无法验证下载文件。应用未被更改。请重试。", "Не удалось проверить загрузку. Приложение не изменено. Повторите попытку."],
        .destinationError: ["この場所にはインストールできません。書き込み可能なフォルダを選んでください。", "Cannot install here. Choose a writable folder.", "이 위치에 설치할 수 없습니다. 쓰기 가능한 폴더를 선택하십시오.", "无法安装到此位置。请选择可写入的文件夹。", "Нельзя установить в эту папку. Выберите папку с правом записи."],
        .runningError: ["SteamAC Liteを終了してから、もう一度試してください。", "Quit SteamAC Lite, then try again.", "SteamAC Lite를 종료한 후 다시 시도하십시오.", "请退出 SteamAC Lite 后重试。", "Закройте SteamAC Lite и повторите попытку."],
        .installError: ["インストールを完了できませんでした。手動ダウンロードから導入してください。SteamOSのディスクと設定は変更していません。", "Installation could not finish. Use the manual download. Your SteamOS disk and settings have not been changed.", "설치를 완료할 수 없습니다. 수동으로 다운로드하여 설치하십시오. SteamOS 디스크와 설정은 변경되지 않았습니다.", "无法完成安装。请手动下载安装。SteamOS 磁盘和设置未被更改。", "Не удалось завершить установку. Скачайте приложение вручную. Диск SteamOS и настройки не изменены."],
        .cancelled: ["インストールを中止しました。", "Installation cancelled.", "설치가 취소되었습니다.", "已取消安装。", "Установка отменена."]
    ]
    func text(_ language: InstallerLanguage, _ arguments: CVarArg...) -> String {
        let index = InstallerLanguage.allCases.firstIndex(of: language)!
        let value = Self.values[self]![index]
        return arguments.isEmpty ? value : String(format: value, locale: Locale(identifier: language.rawValue), arguments: arguments)
    }
}
