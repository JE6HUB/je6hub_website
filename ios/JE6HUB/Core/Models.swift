import Foundation

struct UserSummary: Codable, Hashable {
    /// WanderLens のゲスト (ログインせずにコメントした人) は nil
    let username: String?
    let name: String
    let avatarUrl: String
}

struct FavoriteTrack: Codable, Hashable {
    let title: String
    let artist: String
    let imageUrl: String
    let appleMusicUrl: String
    let previewUrl: String
}

/// ログインしている本人
struct Me: Codable, Hashable {
    let username: String
    let name: String
    let avatarUrl: String
    let displayName: String
    let bio: String
    let location: String
    let website: String
    let email: String
    let favoriteTrack: FavoriteTrack?
    let colorScheme: String
    let notifyMentionsByEmail: Bool
    let hasPassword: Bool
    let isStaff: Bool
    let unreadNotifications: Int
    let webUrl: String

    var summary: UserSummary { UserSummary(username: username, name: name, avatarUrl: avatarUrl) }
}

struct AuthResponse: Decodable {
    let token: String
    let user: Me
}

struct ProfileStats: Codable, Hashable {
    let posts: Int
    let places: Int
    let countries: Int
    let photos: Int
}

struct PublicProfile: Decodable {
    let username: String
    let name: String
    let avatarUrl: String
    let bio: String
    let location: String
    let website: String
    let favoriteTrack: FavoriteTrack?
    let stats: ProfileStats
    let recentPosts: [PostSummary]
    let isSelf: Bool
    let webUrl: String
}

// MARK: - Blogs

struct PostSummary: Codable, Identifiable, Hashable {
    let id: Int
    let title: String
    let subtitle: String
    let excerpt: String
    let coverUrl: String
    let accent: String?
    let author: UserSummary
    let status: String
    let publishedAt: Date?
    let updatedAt: Date?
    let readingMinutes: Int
    let likeCount: Int?
    let commentCount: Int?

    var isDraft: Bool { status == "draft" }
}

struct Page<T: Decodable>: Decodable {
    let results: [T]
    let page: Int
    let hasNext: Bool
}

struct BlogComment: Codable, Identifiable, Hashable {
    let id: Int
    let author: UserSummary
    let text: String
    let createdAt: Date
    let canDelete: Bool
}

struct PostDetail: Decodable {
    let summary: PostSummary
    let bodyHtml: String
    let hasDemo: Bool
    let hasMap: Bool
    let hasMath: Bool
    var liked: Bool
    let isAuthor: Bool
    var comments: [BlogComment]
    let webUrl: String

    private enum CodingKeys: String, CodingKey {
        case bodyHtml, hasDemo, hasMap, hasMath, liked, isAuthor, comments, webUrl
    }

    init(from decoder: Decoder) throws {
        summary = try PostSummary(from: decoder)
        let c = try decoder.container(keyedBy: CodingKeys.self)
        bodyHtml = try c.decode(String.self, forKey: .bodyHtml)
        hasDemo = try c.decode(Bool.self, forKey: .hasDemo)
        hasMap = try c.decode(Bool.self, forKey: .hasMap)
        hasMath = try c.decode(Bool.self, forKey: .hasMath)
        liked = try c.decode(Bool.self, forKey: .liked)
        isAuthor = try c.decode(Bool.self, forKey: .isAuthor)
        comments = try c.decode([BlogComment].self, forKey: .comments)
        webUrl = try c.decode(String.self, forKey: .webUrl)
    }
}

struct LikeResponse: Decodable {
    let liked: Bool
    let likeCount: Int
}

// MARK: - Lounge

struct Channel: Codable, Identifiable, Hashable {
    let id: Int
    let name: String
    let description: String
    let type: String
    let memberCount: Int?
    /// active / pending / invited / nil (未参加)
    let membership: String?
    let role: String?
    let createdAt: Date

    var isPrivate: Bool { type == "private" }
    var isMember: Bool { membership == "active" }
    var canRead: Bool { !isPrivate || isMember }
}

struct ChannelList: Decodable {
    let results: [Channel]
}

struct ChannelMessage: Codable, Identifiable, Hashable {
    let id: Int
    let sender: UserSummary
    let text: String
    let mediaUrl: String
    let mediaType: String?
    let createdAt: Date
}

struct MessagesResponse: Decodable {
    let channel: Channel
    let results: [ChannelMessage]
    let hasMore: Bool
}

// MARK: - WanderLens

struct PinPhoto: Codable, Identifiable, Hashable {
    let id: Int
    let url: String
    let thumbUrl: String
}

struct Pin: Codable, Identifiable, Hashable {
    let id: Int
    let title: String
    let description: String
    let placeName: String
    let country: String
    let visitedOn: String?
    let latitude: Double
    let longitude: Double
    let owner: UserSummary
    let photos: [PinPhoto]
    let commentCount: Int?
    let createdAt: Date
}

struct PinsResponse: Decodable {
    let results: [Pin]
    let maxPhotos: Int
}

struct PinComment: Codable, Identifiable, Hashable {
    let id: Int
    let authorName: String
    let text: String
    let createdAt: Date
}

struct PinCommentsResponse: Decodable {
    let results: [PinComment]
}

// MARK: - 通知

struct NotificationTarget: Codable, Hashable {
    /// post / channel / pin
    let type: String
    let id: Int
}

struct AppNotification: Codable, Identifiable, Hashable {
    let id: Int
    let kind: String
    let place: String
    let message: String
    let excerpt: String
    let actor: UserSummary
    let createdAt: Date
    var read: Bool
    let target: NotificationTarget?
    let webUrl: String
}

struct NotificationsResponse: Decodable {
    let results: [AppNotification]
    let hasMore: Bool
    let unread: Int
}

struct UnreadResponse: Decodable {
    let unread: Int
}

// MARK: - 通報

struct ReportReason: Codable, Hashable {
    let value: String
    let label: String
}

struct ReportReasons: Decodable {
    let reasons: [ReportReason]
}

/// 通報できるもの (サーバーの dashboard.content.KINDS のキー)
enum ReportKind: String {
    case post
    case blogComment = "blog_comment"
    case message
    case pin
    case pinComment = "comment"
}
