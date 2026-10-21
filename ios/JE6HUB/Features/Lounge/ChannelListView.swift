import SwiftUI

struct ChannelListView: View {
    @Environment(Session.self) private var session
    @State private var channels: [Channel] = []
    @State private var loaded = false
    @State private var loadError: Error?
    @State private var error: Error?
    @State private var showCreate = false

    var body: some View {
        Group {
            if !session.isLoggedIn {
                LoginRequiredView(message: "Lounge のチャンネルを見るにはログインしてください。")
            } else if let loadError, channels.isEmpty {
                ErrorView(error: loadError) { await load() }
            } else {
                list
            }
        }
        .navigationTitle("Lounge")
        .toolbar {
            if session.isLoggedIn {
                ToolbarItem(placement: .primaryAction) {
                    Button { showCreate = true } label: { Image(systemName: "plus") }
                        .accessibilityLabel("チャンネルを作成")
                }
            }
        }
        .sheet(isPresented: $showCreate) {
            CreateChannelView { channel in channels.insert(channel, at: 0) }
        }
        .task(id: session.isLoggedIn) { if session.isLoggedIn { await load() } }
        .errorAlert($error)
    }

    private var list: some View {
        List {
            let joined = channels.filter(\.isMember)
            let others = channels.filter { !$0.isMember }
            if !joined.isEmpty {
                Section("参加中") { ForEach(joined) { row($0) } }
            }
            if !others.isEmpty {
                Section("すべてのチャンネル") { ForEach(others) { row($0) } }
            }
        }
        .overlay {
            if !loaded { ProgressView() }
        }
        .refreshable { await load() }
    }

    @ViewBuilder
    private func row(_ channel: Channel) -> some View {
        if channel.canRead {
            NavigationLink(value: Route.channel(channel.id)) { ChannelRow(channel: channel) }
        } else {
            HStack {
                ChannelRow(channel: channel)
                Spacer()
                switch channel.membership {
                case "pending":
                    Text("承認待ち").font(.caption).foregroundStyle(.secondary)
                case "invited":
                    Button("招待を承認") { Task { await join(channel) } }.buttonStyle(.bordered)
                default:
                    Button("参加をリクエスト") { Task { await join(channel) } }.buttonStyle(.bordered)
                }
            }
        }
    }

    private func load() async {
        do {
            let response: ChannelList = try await session.api.get("lounge/channels/")
            channels = response.results
            loadError = nil
        } catch is CancellationError {
        } catch {
            loadError = error
        }
        loaded = true
    }

    private func join(_ channel: Channel) async {
        do {
            let updated: Channel = try await session.api.send("POST", "lounge/channels/\(channel.id)/join/")
            if let index = channels.firstIndex(where: { $0.id == channel.id }) {
                channels[index] = updated
            }
        } catch {
            self.error = error
        }
    }
}

struct ChannelRow: View {
    let channel: Channel

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            HStack(spacing: 6) {
                Image(systemName: channel.isPrivate ? "lock.fill" : "number")
                    .foregroundStyle(.secondary)
                    .font(.caption)
                Text(channel.name).font(.body.weight(.semibold))
            }
            if !channel.description.isEmpty {
                Text(channel.description).font(.caption).foregroundStyle(.secondary).lineLimit(2)
            }
            if let count = channel.memberCount {
                Text("\(count) 人").font(.caption2).foregroundStyle(.secondary)
            }
        }
    }
}

struct CreateChannelView: View {
    let onCreated: (Channel) -> Void

    @Environment(Session.self) private var session
    @Environment(\.dismiss) private var dismiss
    @State private var name = ""
    @State private var description = ""
    @State private var isPrivate = false
    @State private var saving = false
    @State private var error: Error?

    var body: some View {
        NavigationStack {
            Form {
                TextField("チャンネル名", text: $name)
                TextField("説明 (任意)", text: $description, axis: .vertical).lineLimit(2...5)
                Toggle("非公開 (参加にはあなたの承認が必要)", isOn: $isPrivate)
            }
            .navigationTitle("チャンネルを作成")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("キャンセル") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("作成") { Task { await create() } }
                        .disabled(name.trimmingCharacters(in: .whitespaces).isEmpty || saving)
                }
            }
            .errorAlert($error)
        }
    }

    private func create() async {
        saving = true
        defer { saving = false }
        do {
            let channel: Channel = try await session.api.send("POST", "lounge/channels/", json: [
                "name": name, "description": description, "type": isPrivate ? "private" : "public",
            ])
            onCreated(channel)
            dismiss()
        } catch {
            self.error = error
        }
    }
}
