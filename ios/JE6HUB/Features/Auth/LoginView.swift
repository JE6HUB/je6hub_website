import AuthenticationServices
import SwiftUI

/// ログイン画面 (シートで出す)。Web と同じアカウントでログインする。
struct LoginView: View {
    @Environment(Session.self) private var session
    @Environment(\.dismiss) private var dismiss
    @Environment(\.openURL) private var openURL
    @State private var username = ""
    @State private var password = ""
    @State private var loading = false
    @State private var error: Error?

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("ユーザー名またはメールアドレス", text: $username)
                        .textContentType(.username)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                    SecureField("パスワード", text: $password)
                        .textContentType(.password)
                    Button {
                        Task { await login() }
                    } label: {
                        HStack {
                            Text("ログイン")
                            if loading { Spacer(); ProgressView() }
                        }
                    }
                    .disabled(username.isEmpty || password.isEmpty || loading)
                }

                Section {
                    SignInWithAppleButton(.signIn) { request in
                        request.requestedScopes = [.fullName, .email]
                    } onCompletion: { result in
                        Task { await appleCompleted(result) }
                    }
                    .frame(height: 44)
                    .listRowInsets(EdgeInsets())
                }

                Section {
                    Button("アカウントを作成 (Web)") { openURL(AppConfig.webURL("signup/")) }
                    Button("確認メールの再送 (Web)") {
                        openURL(AppConfig.webURL("signup/resend/"))
                    }
                } footer: {
                    Text("アカウントは je6hub.com と共通です。")
                }
            }
            .navigationTitle("ログイン")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("閉じる") { dismiss() }
                }
            }
            .errorAlert($error)
        }
    }

    private func login() async {
        loading = true
        defer { loading = false }
        do {
            try await session.login(username: username.trimmingCharacters(in: .whitespaces), password: password)
            dismiss()
        } catch {
            self.error = error
        }
    }

    private func appleCompleted(_ result: Result<ASAuthorization, Error>) async {
        switch result {
        case .success(let authorization):
            guard let credential = authorization.credential as? ASAuthorizationAppleIDCredential,
                  let tokenData = credential.identityToken,
                  let token = String(data: tokenData, encoding: .utf8) else {
                error = APIError(status: 0, message: "Apple でのサインインに失敗しました。")
                return
            }
            loading = true
            defer { loading = false }
            do {
                try await session.signInWithApple(
                    identityToken: token,
                    firstName: credential.fullName?.givenName,
                    lastName: credential.fullName?.familyName
                )
                dismiss()
            } catch {
                self.error = error
            }
        case .failure(let failure):
            // キャンセルしたときは何も出さない
            if (failure as? ASAuthorizationError)?.code != .canceled {
                error = failure
            }
        }
    }
}
