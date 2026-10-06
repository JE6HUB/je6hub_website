import Foundation
import Observation

/// ログイン状態と、本人の情報。アプリ全体で 1 つ (environment で渡す)。
@MainActor
@Observable
final class Session {
    let api = APIClient()
    private(set) var me: Me?
    private(set) var isRestoring = true
    /// 通知の未読数 (タブのバッジ)
    var unreadNotifications = 0

    var isLoggedIn: Bool { me != nil }

    init() {
        api.onUnauthorized = { [weak self] in self?.clear() }
    }

    /// 起動時: 保存してあるトークンで本人の情報を取り直す。
    func restore() async {
        defer { isRestoring = false }
        guard let token = Keychain.load() else { return }
        api.token = token
        do {
            try await refreshMe()
        } catch let error as APIError where error.status == 401 {
            clear()
        } catch {
            // オフラインなどで確認できなかったときは、ログインしたままにしておく
        }
    }

    func refreshMe() async throws {
        let me: Me = try await api.get("me/")
        update(me)
    }

    func update(_ me: Me) {
        self.me = me
        unreadNotifications = me.unreadNotifications
    }

    func login(username: String, password: String) async throws {
        let response: AuthResponse = try await api.send("POST", "auth/login/", json: [
            "username": username, "password": password, "device_name": deviceName,
        ])
        signedIn(response)
    }

    func signInWithApple(identityToken: String, firstName: String?, lastName: String?) async throws {
        let response: AuthResponse = try await api.send("POST", "auth/apple/", json: [
            "identity_token": identityToken,
            "first_name": firstName ?? "",
            "last_name": lastName ?? "",
            "device_name": deviceName,
        ])
        signedIn(response)
    }

    func logout() async {
        let _: EmptyResponse? = try? await api.send("POST", "auth/logout/")
        clear()
    }

    func deleteAccount(confirm: String) async throws {
        let _: EmptyResponse = try await api.send("DELETE", "me/", json: ["confirm": confirm])
        clear()
    }

    /// アプリに戻ってきたときなどに、未読数を取り直す。
    func refreshUnread() async {
        guard isLoggedIn else { return }
        try? await refreshMe()
    }

    private func signedIn(_ response: AuthResponse) {
        Keychain.save(response.token)
        api.token = response.token
        update(response.user)
    }

    private func clear() {
        Keychain.delete()
        api.token = nil
        me = nil
        unreadNotifications = 0
    }

    private var deviceName: String { "iOS アプリ" }
}
