import Foundation

enum AppConfig {
    /// 稼働中の Web サイトと同じサーバー。API は `/api/v1/` 以下。
    /// 開発中にローカルの Django (docker compose) に向けるときは、スキームの環境変数 `JE6HUB_BASE_URL`
    /// (例: http://localhost:8000) を設定する。
    static let baseURL: URL = {
        #if DEBUG
        if let override = ProcessInfo.processInfo.environment["JE6HUB_BASE_URL"], let url = URL(string: override) {
            return url
        }
        #endif
        return URL(string: "https://je6hub.com")!
    }()

    static var apiURL: URL { baseURL.appendingPathComponent("api/v1/") }

    /// Web のページ (会員登録など)。言語は日本語のページを開く。
    static func webURL(_ path: String) -> URL {
        baseURL.appendingPathComponent("ja/" + path)
    }
}
