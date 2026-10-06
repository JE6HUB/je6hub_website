import SwiftUI

/// Web のヘッダーのベルと同じ通知 (メンション・コメント・返信)
struct NotificationsView: View {
    @Environment(Session.self) private var session
    @Environment(\.openURL) private var openURL
    @State private var items: [AppNotification] = []
    @State private var hasMore = false
    @State private var loaded = false
    @State private var loadError: Error?

    var body: some View {
        Group {
            if !session.isLoggedIn {
                LoginRequiredView(message: "メンションやコメントの通知を見るにはログインしてください。")
            } else if let loadError, items.isEmpty {
                ErrorView(error: loadError) { await load() }
            } else {
                list
            }
        }
        .navigationTitle("通知")
        .toolbar {
            if session.unreadNotifications > 0 {
                ToolbarItem(placement: .primaryAction) {
                    Button("すべて既読") { Task { await readAll() } }
                }
            }
        }
        .task(id: session.isLoggedIn) { if session.isLoggedIn { await load() } }
    }

    private var list: some View {
        List {
            ForEach(items) { item in
                row(item)
            }
            if hasMore {
                Button("さらに読み込む") { Task { await loadMore() } }
            }
        }
        .listStyle(.plain)
        .overlay {
            if !loaded {
                ProgressView()
            } else if items.isEmpty {
                ContentUnavailableView("通知はありません", systemImage: "bell.slash")
            }
        }
        .refreshable { await load() }
    }

    @ViewBuilder
    private func row(_ item: AppNotification) -> some View {
        let label = NotificationRow(item: item)
        if let route = Route(target: item.target) {
            NavigationLink(value: route) { label }
                .simultaneousGesture(TapGesture().onEnded { Task { await markRead(item) } })
        } else {
            // アプリにない画面 (将来の通知の種類など) は Web で開く
            Button {
                Task { await markRead(item) }
                if let url = URL(string: item.webUrl) { openURL(url) }
            } label: { label }
            .buttonStyle(.plain)
        }
    }

    private func load() async {
        do {
            let response: NotificationsResponse = try await session.api.get("notifications/")
            items = response.results
            hasMore = response.hasMore
            session.unreadNotifications = response.unread
            loadError = nil
        } catch is CancellationError {
        } catch {
            loadError = error
        }
        loaded = true
    }

    private func loadMore() async {
        guard let last = items.last?.id,
              let response: NotificationsResponse = try? await session.api.get("notifications/", query: ["before": String(last)])
        else { return }
        items += response.results
        hasMore = response.hasMore
    }

    private func markRead(_ item: AppNotification) async {
        guard !item.read else { return }
        guard let response: UnreadResponse = try? await session.api.send("POST", "notifications/\(item.id)/read/") else { return }
        if let index = items.firstIndex(where: { $0.id == item.id }) { items[index].read = true }
        session.unreadNotifications = response.unread
    }

    private func readAll() async {
        guard let _: UnreadResponse = try? await session.api.send("POST", "notifications/read/") else { return }
        for index in items.indices { items[index].read = true }
        session.unreadNotifications = 0
    }
}

struct NotificationRow: View {
    let item: AppNotification

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            AvatarView(user: item.actor, size: 36)
            VStack(alignment: .leading, spacing: 4) {
                Text(item.message).font(.subheadline).fontWeight(item.read ? .regular : .semibold)
                if !item.excerpt.isEmpty {
                    Text(item.excerpt).font(.caption).foregroundStyle(.secondary).lineLimit(2)
                }
                Text(item.createdAt.relative).font(.caption2).foregroundStyle(.secondary)
            }
            Spacer(minLength: 0)
            if !item.read {
                Circle().fill(Color.accentColor).frame(width: 8, height: 8).padding(.top, 6)
            }
        }
        .padding(.vertical, 2)
    }
}
