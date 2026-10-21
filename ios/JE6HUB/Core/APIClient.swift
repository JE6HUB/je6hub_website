import Foundation

struct APIError: LocalizedError {
    let status: Int
    let message: String
    /// サーバーが返したフィールドごとのエラー ({"website": ["..."]})
    var fieldErrors: [String: [String]] = [:]

    var errorDescription: String? { message }

    static let network = APIError(status: 0, message: "サーバーに接続できませんでした。通信環境を確認してください。")
}

/// `{}` だけを返す API 用
struct EmptyResponse: Decodable {}

/// multipart で送るファイル
struct UploadFile {
    let field: String
    let filename: String
    let mimeType: String
    let data: Data
}

/// je6hub.com の `/api/v1/` を呼ぶ。トークンは `Authorization: Bearer` で送る。
final class APIClient {
    var token: String?
    /// トークンが無効になったとき (ログアウト・退会・凍結) に呼ばれる
    var onUnauthorized: (@MainActor () -> Void)?

    private let session: URLSession = {
        let config = URLSessionConfiguration.default
        // API はクッキーを使わない
        config.httpCookieAcceptPolicy = .never
        config.httpShouldSetCookies = false
        config.timeoutIntervalForRequest = 30
        return URLSession(configuration: config)
    }()

    static let decoder: JSONDecoder = {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        decoder.dateDecodingStrategy = .custom { decoder in
            let container = try decoder.singleValueContainer()
            let string = try container.decode(String.self)
            if let date = formatter.date(from: string) {
                return date
            }
            throw DecodingError.dataCorruptedError(in: container, debugDescription: "Invalid date: \(string)")
        }
        return decoder
    }()

    // MARK: - リクエスト

    func get<T: Decodable>(_ path: String, query: [String: String] = [:]) async throws -> T {
        try await perform(makeRequest("GET", path, query: query))
    }

    func send<T: Decodable>(_ method: String, _ path: String, json: [String: Any]? = nil) async throws -> T {
        var request = makeRequest(method, path)
        if let json {
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try JSONSerialization.data(withJSONObject: json)
        }
        return try await perform(request)
    }

    func upload<T: Decodable>(_ path: String, method: String = "POST", fields: [String: String], files: [UploadFile]) async throws -> T {
        var request = makeRequest(method, path)
        let boundary = "je6hub-\(UUID().uuidString)"
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        var body = Data()
        func append(_ string: String) { body.append(Data(string.utf8)) }
        for (name, value) in fields {
            append("--\(boundary)\r\n")
            append("Content-Disposition: form-data; name=\"\(name)\"\r\n\r\n")
            append("\(value)\r\n")
        }
        for file in files {
            append("--\(boundary)\r\n")
            append("Content-Disposition: form-data; name=\"\(file.field)\"; filename=\"\(file.filename)\"\r\n")
            append("Content-Type: \(file.mimeType)\r\n\r\n")
            body.append(file.data)
            append("\r\n")
        }
        append("--\(boundary)--\r\n")
        request.httpBody = body
        request.timeoutInterval = 300
        return try await perform(request)
    }

    // MARK: - 内部

    private func makeRequest(_ method: String, _ path: String, query: [String: String] = [:]) -> URLRequest {
        var components = URLComponents(url: AppConfig.apiURL.appendingPathComponent(path), resolvingAgainstBaseURL: false)!
        // appendingPathComponent は末尾の / を落とすことがあるので付け直す (Django の URL は / で終わる)
        if !components.path.hasSuffix("/") {
            components.path += "/"
        }
        if !query.isEmpty {
            components.queryItems = query.sorted { $0.key < $1.key }.map { URLQueryItem(name: $0.key, value: $0.value) }
        }
        var request = URLRequest(url: components.url!)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if let token {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        return request
    }

    private func perform<T: Decodable>(_ request: URLRequest) async throws -> T {
        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: request)
        } catch {
            if (error as? URLError)?.code == .cancelled {
                throw CancellationError()
            }
            throw APIError.network
        }
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        guard (200..<300).contains(status) else {
            let body = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
            let message = body?["error"] as? String ?? "エラーが発生しました (\(status))"
            let fieldErrors = body?["errors"] as? [String: [String]] ?? [:]
            if status == 401, token != nil {
                await MainActor.run { onUnauthorized?() }
            }
            throw APIError(status: status, message: message, fieldErrors: fieldErrors)
        }
        return try Self.decoder.decode(T.self, from: data)
    }
}
