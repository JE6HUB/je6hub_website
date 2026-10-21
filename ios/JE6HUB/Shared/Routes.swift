import SwiftUI

/// 画面遷移先。どのタブの NavigationStack からでも同じ画面を開けるようにする。
enum Route: Hashable {
    case post(Int)
    case user(String)
    case channel(Int)
    case pin(Int)

    init?(target: NotificationTarget?) {
        switch target?.type {
        case "post": self = .post(target!.id)
        case "channel": self = .channel(target!.id)
        case "pin": self = .pin(target!.id)
        default: return nil
        }
    }
}

extension View {
    func withRoutes() -> some View {
        navigationDestination(for: Route.self) { route in
            switch route {
            case .post(let id): PostDetailView(postID: id)
            case .user(let username): UserProfileView(username: username)
            case .channel(let id): ChannelView(channelID: id)
            case .pin(let id): PinDetailView(pinID: id)
            }
        }
    }
}
