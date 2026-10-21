import SwiftUI

struct RootView: View {
    @Environment(Session.self) private var session
    @Environment(\.scenePhase) private var scenePhase

    var body: some View {
        if session.isRestoring {
            ProgressView()
        } else {
            TabView {
                NavigationStack { BlogListView().withRoutes() }
                    .tabItem { Label("Blogs", systemImage: "book") }
                NavigationStack { ChannelListView().withRoutes() }
                    .tabItem { Label("Lounge", systemImage: "bubble.left.and.bubble.right") }
                NavigationStack { WanderLensView().withRoutes() }
                    .tabItem { Label("WanderLens", systemImage: "map") }
                NavigationStack { NotificationsView().withRoutes() }
                    .tabItem { Label("通知", systemImage: "bell") }
                    .badge(session.unreadNotifications)
                NavigationStack { MyPageView().withRoutes() }
                    .tabItem { Label("マイページ", systemImage: "person.crop.circle") }
            }
            .onChange(of: scenePhase) { _, phase in
                if phase == .active {
                    Task { await session.refreshUnread() }
                }
            }
        }
    }
}
