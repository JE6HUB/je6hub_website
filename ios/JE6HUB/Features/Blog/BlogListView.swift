import SwiftUI

struct BlogListView: View {
    @Environment(Session.self) private var session
    @State private var posts: [PostSummary] = []
    @State private var page = 0
    @State private var hasNext = true
    @State private var query = ""
    @State private var loading = false
    @State private var error: Error?

    var body: some View {
        List {
            ForEach(posts) { post in
                NavigationLink(value: Route.post(post.id)) {
                    PostRow(post: post)
                }
                .onAppear {
                    if post.id == posts.last?.id { Task { await loadMore() } }
                }
            }
            if loading {
                HStack { Spacer(); ProgressView(); Spacer() }
            }
        }
        .listStyle(.plain)
        .overlay {
            if let error, posts.isEmpty {
                ErrorView(error: error) { await reload() }
            } else if !loading && posts.isEmpty {
                ContentUnavailableView(query.isEmpty ? "記事はまだありません" : "見つかりませんでした",
                                       systemImage: "book")
            }
        }
        .navigationTitle("Blogs")
        .searchable(text: $query, prompt: "記事を検索")
        .onSubmit(of: .search) { Task { await reload() } }
        .onChange(of: query) { _, value in
            if value.isEmpty { Task { await reload() } }
        }
        .refreshable { await reload() }
        .task { if posts.isEmpty { await reload() } }
    }

    private func reload() async {
        page = 0
        hasNext = true
        await load(reset: true)
    }

    private func loadMore() async {
        guard hasNext, !loading else { return }
        await load(reset: false)
    }

    private func load(reset: Bool) async {
        loading = true
        defer { loading = false }
        do {
            var params = ["page": String(page + 1)]
            if !query.isEmpty { params["q"] = query }
            let result: Page<PostSummary> = try await session.api.get("blog/posts/", query: params)
            posts = reset ? result.results : posts + result.results
            page = result.page
            hasNext = result.hasNext
            error = nil
        } catch is CancellationError {
        } catch {
            self.error = error
        }
    }
}

struct PostRow: View {
    let post: PostSummary

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 6) {
                if post.isDraft {
                    Text("下書き").font(.caption2.weight(.bold)).foregroundStyle(.orange)
                }
                Text(post.title).font(.headline).lineLimit(2)
                Text(post.excerpt).font(.subheadline).foregroundStyle(.secondary).lineLimit(2)
                HStack(spacing: 10) {
                    Text(post.author.name)
                    if let date = post.publishedAt ?? post.updatedAt {
                        Text(date, format: .dateTime.month().day())
                    }
                    if let likes = post.likeCount, likes > 0 {
                        Label("\(likes)", systemImage: "heart")
                    }
                    if let comments = post.commentCount, comments > 0 {
                        Label("\(comments)", systemImage: "bubble.right")
                    }
                }
                .font(.caption)
                .foregroundStyle(.secondary)
            }
            Spacer(minLength: 0)
            if !post.coverUrl.isEmpty {
                RemoteImage(url: post.coverUrl)
                    .frame(width: 84, height: 84)
                    .clipShape(RoundedRectangle(cornerRadius: 10))
            }
        }
        .padding(.vertical, 4)
    }
}
