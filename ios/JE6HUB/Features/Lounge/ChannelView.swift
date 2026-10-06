import AVKit
import PhotosUI
import SwiftUI

/// チャンネルの会話。開いている間は数秒ごとに新しいメッセージを取りに行く。
struct ChannelView: View {
    let channelID: Int

    @Environment(Session.self) private var session
    @State private var channel: Channel?
    @State private var messages: [ChannelMessage] = []
    @State private var hasMore = false
    @State private var loadError: Error?
    @State private var error: Error?
    @State private var text = ""
    @State private var attachment: PhotosPickerItem?
    @State private var sending = false
    @State private var playing: PlayingVideo?
    @State private var reportID: Int?

    var body: some View {
        Group {
            if let loadError, channel == nil {
                ErrorView(error: loadError) { await loadLatest() }
            } else {
                conversation
            }
        }
        .navigationTitle(channel?.name ?? "")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            if let channel, channel.isMember, channel.role != "owner" {
                ToolbarItem(placement: .primaryAction) {
                    Menu {
                        Button(role: .destructive) { Task { await leave() } } label: {
                            Label("チャンネルから退出", systemImage: "rectangle.portrait.and.arrow.right")
                        }
                    } label: { Image(systemName: "ellipsis.circle") }
                }
            }
        }
        .task { await poll() }
        .errorAlert($error)
        .sheet(item: $playing) { video in
            VideoPlayer(player: AVPlayer(url: video.url)).ignoresSafeArea()
        }
        .sheet(isPresented: Binding(get: { reportID != nil }, set: { if !$0 { reportID = nil } })) {
            if let reportID { ReportSheet(kind: .message, objectID: reportID) }
        }
    }

    private var conversation: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 14) {
                    if hasMore {
                        Button("さらに読み込む") { Task { await loadOlder() } }
                            .frame(maxWidth: .infinity)
                    }
                    ForEach(messages) { message in
                        MessageRow(message: message, isMine: message.sender.username == session.me?.username,
                                   play: { playing = PlayingVideo(url: $0) }, report: { reportID = message.id })
                            .id(message.id)
                    }
                }
                .padding()
            }
            .defaultScrollAnchor(.bottom)
            .onChange(of: messages.last?.id) { _, id in
                if let id { withAnimation { proxy.scrollTo(id, anchor: .bottom) } }
            }
        }
        .safeAreaInset(edge: .bottom) { composer }
    }

    private var composer: some View {
        VStack(spacing: 6) {
            if attachment != nil {
                HStack {
                    Label("添付があります", systemImage: "paperclip").font(.caption)
                    Button { attachment = nil } label: { Image(systemName: "xmark.circle.fill") }
                    Spacer()
                }
                .foregroundStyle(.secondary)
            }
            HStack(alignment: .bottom, spacing: 8) {
                PhotosPicker(selection: $attachment, matching: .any(of: [.images, .videos])) {
                    Image(systemName: "photo.on.rectangle").font(.title3)
                }
                TextField("メッセージ", text: $text, axis: .vertical)
                    .lineLimit(1...5)
                    .textFieldStyle(.roundedBorder)
                Button {
                    Task { await send() }
                } label: {
                    if sending { ProgressView() } else { Image(systemName: "paperplane.fill").font(.title3) }
                }
                .disabled(sending || (text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && attachment == nil))
            }
        }
        .padding(.horizontal)
        .padding(.vertical, 8)
        .background(.bar)
    }

    // MARK: - 読み込み

    private func poll() async {
        await loadLatest()
        while !Task.isCancelled {
            try? await Task.sleep(for: .seconds(5))
            guard !Task.isCancelled else { break }
            await loadNewer()
        }
    }

    private func loadLatest() async {
        do {
            let response: MessagesResponse = try await session.api.get("lounge/channels/\(channelID)/messages/")
            channel = response.channel
            messages = response.results
            hasMore = response.hasMore
            loadError = nil
        } catch is CancellationError {
        } catch {
            loadError = error
        }
    }

    private func loadNewer() async {
        guard let last = messages.last?.id else { return await loadLatest() }
        guard let response: MessagesResponse = try? await session.api.get(
            "lounge/channels/\(channelID)/messages/", query: ["after": String(last)]) else { return }
        append(response.results)
    }

    private func loadOlder() async {
        guard let first = messages.first?.id else { return }
        do {
            let response: MessagesResponse = try await session.api.get(
                "lounge/channels/\(channelID)/messages/", query: ["before": String(first)])
            messages.insert(contentsOf: response.results, at: 0)
            hasMore = response.hasMore
        } catch {
            self.error = error
        }
    }

    private func append(_ new: [ChannelMessage]) {
        let known = Set(messages.map(\.id))
        messages += new.filter { !known.contains($0.id) }
    }

    // MARK: - 送信

    private func send() async {
        sending = true
        defer { sending = false }
        do {
            let message: ChannelMessage
            if let attachment {
                let file = try await MediaLoader.upload(attachment, field: "media")
                message = try await session.api.upload("lounge/channels/\(channelID)/messages/",
                                                       fields: ["text": text], files: [file])
            } else {
                message = try await session.api.send("POST", "lounge/channels/\(channelID)/messages/",
                                                     json: ["text": text])
            }
            append([message])
            text = ""
            attachment = nil
        } catch {
            self.error = error
        }
    }

    private func leave() async {
        do {
            channel = try await session.api.send("POST", "lounge/channels/\(channelID)/leave/")
        } catch {
            self.error = error
        }
    }
}

/// 再生する動画 (sheet(item:) 用)
struct PlayingVideo: Identifiable {
    let url: URL
    var id: String { url.absoluteString }
}

struct MessageRow: View {
    let message: ChannelMessage
    let isMine: Bool
    let play: (URL) -> Void
    let report: () -> Void

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            NavigationLink(value: Route.user(message.sender.username ?? "")) {
                AvatarView(user: message.sender, size: 34)
            }
            .buttonStyle(.plain)
            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 6) {
                    Text(message.sender.name).font(.subheadline.weight(.semibold))
                    Text(message.createdAt, format: .dateTime.month().day().hour().minute())
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                if !message.text.isEmpty {
                    Text(message.text).textSelection(.enabled)
                }
                if let url = URL(string: message.mediaUrl), !message.mediaUrl.isEmpty {
                    if message.mediaType == "video" {
                        Button { play(url) } label: {
                            Label("動画を再生", systemImage: "play.rectangle.fill")
                        }
                        .buttonStyle(.bordered)
                    } else {
                        RemoteImage(url: message.mediaUrl, contentMode: .fit)
                            .frame(maxWidth: 260, maxHeight: 260, alignment: .leading)
                            .clipShape(RoundedRectangle(cornerRadius: 10))
                    }
                }
            }
            Spacer(minLength: 0)
        }
        .contextMenu {
            if !message.text.isEmpty {
                Button { UIPasteboard.general.string = message.text } label: { Label("コピー", systemImage: "doc.on.doc") }
            }
            if !isMine {
                Button(role: .destructive, action: report) { Label("通報", systemImage: "exclamationmark.bubble") }
            }
        }
    }
}
