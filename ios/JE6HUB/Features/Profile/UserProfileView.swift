import SwiftUI

/// ほかのユーザーの公開プロフィール
struct UserProfileView: View {
    let username: String

    @Environment(Session.self) private var session
    @Environment(\.openURL) private var openURL
    @State private var profile: PublicProfile?
    @State private var loadError: Error?

    var body: some View {
        Group {
            if let profile {
                List {
                    Section {
                        HStack(spacing: 14) {
                            AvatarView(user: UserSummary(username: profile.username, name: profile.name,
                                                         avatarUrl: profile.avatarUrl), size: 72)
                            VStack(alignment: .leading, spacing: 3) {
                                Text(profile.name).font(.title3.bold())
                                Text("@\(profile.username)").font(.subheadline).foregroundStyle(.secondary)
                                if !profile.location.isEmpty {
                                    Label(profile.location, systemImage: "mappin").font(.caption).foregroundStyle(.secondary)
                                }
                            }
                        }
                        if !profile.bio.isEmpty { Text(profile.bio) }
                        if let url = URL(string: profile.website), !profile.website.isEmpty {
                            Link(profile.website, destination: url).font(.subheadline)
                        }
                        HStack {
                            stat(profile.stats.posts, "記事")
                            stat(profile.stats.places, "スポット")
                            stat(profile.stats.countries, "か国")
                            stat(profile.stats.photos, "写真")
                        }
                    }
                    if let track = profile.favoriteTrack {
                        Section("お気に入りの曲") {
                            HStack(spacing: 12) {
                                RemoteImage(url: track.imageUrl).frame(width: 52, height: 52)
                                    .clipShape(RoundedRectangle(cornerRadius: 6))
                                VStack(alignment: .leading) {
                                    Text(track.title).font(.subheadline.weight(.semibold))
                                    Text(track.artist).font(.caption).foregroundStyle(.secondary)
                                }
                                Spacer()
                                if let url = URL(string: track.appleMusicUrl), !track.appleMusicUrl.isEmpty {
                                    Button { openURL(url) } label: { Image(systemName: "play.circle.fill").font(.title2) }
                                        .buttonStyle(.plain)
                                }
                            }
                        }
                    }
                    if !profile.recentPosts.isEmpty {
                        Section("最近の記事") {
                            ForEach(profile.recentPosts) { post in
                                NavigationLink(value: Route.post(post.id)) { PostRow(post: post) }
                            }
                        }
                    }
                }
            } else if let loadError {
                ErrorView(error: loadError) { await load() }
            } else {
                ProgressView()
            }
        }
        .navigationTitle(profile?.name ?? "")
        .navigationBarTitleDisplayMode(.inline)
        .task { await load() }
    }

    private func stat(_ value: Int, _ label: String) -> some View {
        VStack {
            Text("\(value)").font(.headline)
            Text(label).font(.caption2).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
    }

    private func load() async {
        do {
            profile = try await session.api.get("users/\(username)/")
            loadError = nil
        } catch is CancellationError {
        } catch {
            loadError = error
        }
    }
}
