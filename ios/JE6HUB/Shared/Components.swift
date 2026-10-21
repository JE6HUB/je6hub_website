import SwiftUI

/// ユーザー画像 (未設定なら名前の頭文字)
struct AvatarView: View {
    let user: UserSummary?
    var size: CGFloat = 32

    var body: some View {
        Group {
            if let url = URL(string: user?.avatarUrl ?? ""), !(user?.avatarUrl ?? "").isEmpty {
                AsyncImage(url: url) { image in
                    image.resizable().scaledToFill()
                } placeholder: {
                    placeholder
                }
            } else {
                placeholder
            }
        }
        .frame(width: size, height: size)
        .clipShape(Circle())
        .accessibilityHidden(true)
    }

    private var placeholder: some View {
        ZStack {
            Circle().fill(Color.accentColor.opacity(0.25))
            Text(String((user?.name ?? "?").prefix(1)).uppercased())
                .font(.system(size: size * 0.45, weight: .semibold))
                .foregroundStyle(.primary)
        }
    }
}

/// URL の画像を、読み込み中はグレーの枠で表示する
struct RemoteImage: View {
    let url: String
    var contentMode: ContentMode = .fill

    var body: some View {
        AsyncImage(url: URL(string: url)) { phase in
            switch phase {
            case .success(let image):
                image.resizable().aspectRatio(contentMode: contentMode)
            case .failure:
                Color.secondary.opacity(0.15).overlay(Image(systemName: "photo").foregroundStyle(.secondary))
            default:
                Color.secondary.opacity(0.15)
            }
        }
    }
}

/// 名前とユーザー画像。ユーザー名があればプロフィールへ移動できる
struct AuthorLabel: View {
    let user: UserSummary
    var date: Date?

    var body: some View {
        HStack(spacing: 8) {
            AvatarView(user: user, size: 28)
            VStack(alignment: .leading, spacing: 1) {
                Text(user.name).font(.subheadline.weight(.semibold))
                if let date {
                    Text(date, format: .dateTime.year().month().day())
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
        }
    }
}

/// ログインが必要な画面の代わりに出す案内
struct LoginRequiredView: View {
    let message: String
    @State private var showLogin = false

    var body: some View {
        ContentUnavailableView {
            Label("ログインが必要です", systemImage: "person.crop.circle")
        } description: {
            Text(message)
        } actions: {
            Button("ログイン") { showLogin = true }
                .buttonStyle(.borderedProminent)
        }
        .sheet(isPresented: $showLogin) { LoginView() }
    }
}

/// 読み込みに失敗したときの表示 (再試行ボタン付き)
struct ErrorView: View {
    let error: Error
    let retry: () async -> Void

    var body: some View {
        ContentUnavailableView {
            Label("読み込めませんでした", systemImage: "exclamationmark.triangle")
        } description: {
            Text(error.localizedDescription)
        } actions: {
            Button("再試行") { Task { await retry() } }
        }
    }
}

extension Date {
    /// 「3 分前」のような相対表記
    var relative: String {
        RelativeDateTimeFormatter().localizedString(for: self, relativeTo: .now)
    }
}

extension View {
    /// エラーを OK だけのアラートで出す
    func errorAlert(_ error: Binding<Error?>) -> some View {
        alert(
            "エラー",
            isPresented: Binding(get: { error.wrappedValue != nil }, set: { if !$0 { error.wrappedValue = nil } }),
            presenting: error.wrappedValue
        ) { _ in
            Button("OK", role: .cancel) {}
        } message: { error in
            Text(error.localizedDescription)
        }
    }
}
