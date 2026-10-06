import SwiftUI

struct PostDetailView: View {
    let postID: Int

    @Environment(Session.self) private var session
    @Environment(\.openURL) private var openURL
    @State private var post: PostDetail?
    @State private var bodyHeight: CGFloat = 200
    @State private var loadError: Error?
    @State private var error: Error?
    @State private var commentText = ""
    @State private var replyTo: BlogComment?
    @State private var sending = false
    @State private var showLogin = false
    @State private var report: (kind: ReportKind, id: Int)?

    var body: some View {
        Group {
            if let post {
                content(post)
            } else if let loadError {
                ErrorView(error: loadError) { await load() }
            } else {
                ProgressView()
            }
        }
        .navigationBarTitleDisplayMode(.inline)
        .task { await load() }
        .errorAlert($error)
        .sheet(isPresented: $showLogin) { LoginView() }
        .sheet(isPresented: Binding(get: { report != nil }, set: { if !$0 { report = nil } })) {
            if let report { ReportSheet(kind: report.kind, objectID: report.id) }
        }
    }

    private func content(_ post: PostDetail) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                if !post.summary.coverUrl.isEmpty {
                    RemoteImage(url: post.summary.coverUrl)
                        .frame(maxWidth: .infinity)
                        .frame(height: 220)
                        .clipped()
                }
                VStack(alignment: .leading, spacing: 12) {
                    Text(post.summary.title).font(.title.bold())
                    if !post.summary.subtitle.isEmpty {
                        Text(post.summary.subtitle).font(.title3).foregroundStyle(.secondary)
                    }
                    NavigationLink(value: Route.user(post.summary.author.username ?? "")) {
                        AuthorLabel(user: post.summary.author, date: post.summary.publishedAt)
                    }
                    .buttonStyle(.plain)
                    Text("\(post.summary.readingMinutes) 分で読めます").font(.caption).foregroundStyle(.secondary)

                    if post.hasDemo || post.hasMap || post.hasMath {
                        Button {
                            if let url = URL(string: post.webUrl) { openURL(url) }
                        } label: {
                            Label("動くデモや地図は Web 版で見られます", systemImage: "safari")
                                .font(.subheadline)
                        }
                    }

                    HTMLView(html: post.bodyHtml, height: $bodyHeight)
                        .frame(height: bodyHeight)

                    reactions(post)
                    Divider()
                    comments(post)
                }
                .padding(.horizontal)
            }
            .padding(.bottom, 32)
        }
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Menu {
                    if let url = URL(string: post.webUrl) {
                        ShareLink(item: url)
                        Button { openURL(url) } label: { Label("Web で開く", systemImage: "safari") }
                    }
                    if session.isLoggedIn && !post.isAuthor {
                        Button(role: .destructive) { report = (.post, post.summary.id) } label: {
                            Label("記事を通報", systemImage: "exclamationmark.bubble")
                        }
                    }
                } label: {
                    Image(systemName: "ellipsis.circle")
                }
            }
        }
    }

    private func reactions(_ post: PostDetail) -> some View {
        HStack(spacing: 20) {
            Button {
                Task { await toggleLike() }
            } label: {
                Label("\(post.summary.likeCount ?? 0)", systemImage: post.liked ? "heart.fill" : "heart")
                    .foregroundStyle(post.liked ? .pink : .primary)
            }
            .disabled(post.summary.isDraft)
            Label("\(post.comments.count)", systemImage: "bubble.right")
        }
        .font(.title3)
        .buttonStyle(.plain)
        .padding(.top, 8)
    }

    private func comments(_ post: PostDetail) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("コメント").font(.headline)
            ForEach(post.comments) { comment in
                VStack(alignment: .leading, spacing: 6) {
                    HStack {
                        NavigationLink(value: Route.user(comment.author.username ?? "")) {
                            AuthorLabel(user: comment.author)
                        }
                        .buttonStyle(.plain)
                        Spacer()
                        Text(comment.createdAt.relative).font(.caption).foregroundStyle(.secondary)
                        Menu {
                            if session.isLoggedIn {
                                Button { replyTo = comment } label: { Label("返信", systemImage: "arrowshape.turn.up.left") }
                            }
                            if comment.canDelete {
                                Button(role: .destructive) { Task { await delete(comment) } } label: {
                                    Label("削除", systemImage: "trash")
                                }
                            } else if session.isLoggedIn {
                                Button(role: .destructive) { report = (.blogComment, comment.id) } label: {
                                    Label("通報", systemImage: "exclamationmark.bubble")
                                }
                            }
                        } label: {
                            Image(systemName: "ellipsis").padding(6)
                        }
                    }
                    Text(comment.text).font(.body).textSelection(.enabled)
                }
                .id(comment.id)
            }
            if post.summary.isDraft {
                Text("下書きにはコメントできません。").font(.footnote).foregroundStyle(.secondary)
            } else if session.isLoggedIn {
                commentForm
            } else {
                Button("ログインしてコメントする") { showLogin = true }
            }
        }
    }

    private var commentForm: some View {
        VStack(alignment: .leading, spacing: 8) {
            if let replyTo {
                HStack {
                    Text("\(replyTo.author.name) さんへの返信").font(.caption).foregroundStyle(.secondary)
                    Button { self.replyTo = nil } label: { Image(systemName: "xmark.circle.fill") }
                        .buttonStyle(.plain)
                        .foregroundStyle(.secondary)
                }
            }
            TextField("コメントを書く (@ユーザー名 でメンション)", text: $commentText, axis: .vertical)
                .lineLimit(2...6)
                .textFieldStyle(.roundedBorder)
            Button("送信") { Task { await sendComment() } }
                .buttonStyle(.borderedProminent)
                .disabled(commentText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || sending)
        }
    }

    // MARK: - 操作

    private func load() async {
        do {
            post = try await session.api.get("blog/posts/\(postID)/")
            loadError = nil
        } catch is CancellationError {
        } catch {
            loadError = error
        }
    }

    private func toggleLike() async {
        guard session.isLoggedIn else { showLogin = true; return }
        guard let current = post else { return }
        do {
            let result: LikeResponse = try await session.api.send(current.liked ? "DELETE" : "POST",
                                                                  "blog/posts/\(postID)/like/")
            post?.liked = result.liked
            await load()
        } catch {
            self.error = error
        }
    }

    private func sendComment() async {
        sending = true
        defer { sending = false }
        var body: [String: Any] = ["text": commentText]
        if let replyTo { body["reply_to"] = replyTo.id }
        do {
            let comment: BlogComment = try await session.api.send("POST", "blog/posts/\(postID)/comments/", json: body)
            post?.comments.append(comment)
            commentText = ""
            replyTo = nil
        } catch {
            self.error = error
        }
    }

    private func delete(_ comment: BlogComment) async {
        do {
            let _: EmptyResponse = try await session.api.send("DELETE", "blog/comments/\(comment.id)/")
            post?.comments.removeAll { $0.id == comment.id }
        } catch {
            self.error = error
        }
    }
}
