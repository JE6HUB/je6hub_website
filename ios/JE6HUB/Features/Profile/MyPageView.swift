import PhotosUI
import SwiftUI

/// マイページ: 自分のプロフィール・記事、設定、ログアウト、退会
struct MyPageView: View {
    @Environment(Session.self) private var session
    @Environment(\.openURL) private var openURL
    @State private var showEdit = false
    @State private var showDelete = false
    @State private var myPosts: [PostSummary] = []

    var body: some View {
        Group {
            if let me = session.me {
                List {
                    Section {
                        HStack(spacing: 14) {
                            AvatarView(user: me.summary, size: 64)
                            VStack(alignment: .leading, spacing: 3) {
                                Text(me.name).font(.title3.bold())
                                Text("@\(me.username)").font(.subheadline).foregroundStyle(.secondary)
                            }
                        }
                        if !me.bio.isEmpty { Text(me.bio).font(.subheadline) }
                        NavigationLink(value: Route.user(me.username)) { Text("公開プロフィールを見る") }
                        Button("プロフィールを編集") { showEdit = true }
                    }

                    Section {
                        ForEach(myPosts) { post in
                            NavigationLink(value: Route.post(post.id)) { PostRow(post: post) }
                        }
                        Button {
                            openURL(AppConfig.webURL("blog/new/"))
                        } label: {
                            Label("記事を書く (Web のエディタ)", systemImage: "square.and.pencil")
                        }
                    } header: {
                        Text("自分の記事")
                    } footer: {
                        Text("記事の作成・編集は、ブロックエディタのある Web 版で行えます。")
                    }

                    Section("設定") {
                        Button("カラースキーム・お気に入りの曲など (Web)") { openURL(AppConfig.webURL("settings/")) }
                        Button("お問い合わせ (Web)") { openURL(AppConfig.webURL("contact/")) }
                    }

                    Section {
                        Button("ログアウト") { Task { await session.logout() } }
                        if !me.isStaff {
                            Button("退会する", role: .destructive) { showDelete = true }
                        }
                    }
                }
                .refreshable {
                    try? await session.refreshMe()
                    await loadPosts()
                }
                .task { await loadPosts() }
                .sheet(isPresented: $showEdit) { EditProfileView(me: me) }
                .sheet(isPresented: $showDelete) { DeleteAccountView(me: me) }
            } else {
                LoginRequiredView(message: "je6hub.com のアカウントでログインできます。")
            }
        }
        .navigationTitle("マイページ")
    }

    private func loadPosts() async {
        if let page: Page<PostSummary> = try? await session.api.get("blog/posts/mine/") {
            myPosts = page.results
        }
    }
}

struct EditProfileView: View {
    let me: Me

    @Environment(Session.self) private var session
    @Environment(\.dismiss) private var dismiss
    @State private var displayName = ""
    @State private var bio = ""
    @State private var location = ""
    @State private var website = ""
    @State private var notifyByEmail = true
    @State private var avatarItem: PhotosPickerItem?
    @State private var saving = false
    @State private var error: Error?

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    HStack {
                        AvatarView(user: session.me?.summary ?? me.summary, size: 64)
                        PhotosPicker(selection: $avatarItem, matching: .images) { Text("ユーザー画像を変更") }
                    }
                    if !(session.me?.avatarUrl ?? "").isEmpty {
                        Button("ユーザー画像を削除", role: .destructive) { Task { await removeAvatar() } }
                    }
                }
                Section("公開プロフィール") {
                    TextField("表示名", text: $displayName)
                    TextField("自己紹介", text: $bio, axis: .vertical).lineLimit(3...6)
                    TextField("拠点", text: $location)
                    TextField("ウェブサイト", text: $website)
                        .keyboardType(.URL)
                        .textInputAutocapitalization(.never)
                }
                Section("通知") {
                    Toggle("メンションをメールで受け取る", isOn: $notifyByEmail)
                }
            }
            .navigationTitle("プロフィールを編集")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("キャンセル") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("保存") { Task { await save() } }.disabled(saving)
                }
            }
            .onAppear {
                displayName = me.displayName
                bio = me.bio
                location = me.location
                website = me.website
                notifyByEmail = me.notifyMentionsByEmail
            }
            .onChange(of: avatarItem) { _, item in
                if let item { Task { await uploadAvatar(item) } }
            }
            .errorAlert($error)
        }
    }

    private func save() async {
        saving = true
        defer { saving = false }
        do {
            let updated: Me = try await session.api.send("PATCH", "me/", json: [
                "display_name": displayName, "bio": bio, "location": location, "website": website,
                "notify_mentions_by_email": notifyByEmail,
            ])
            session.update(updated)
            dismiss()
        } catch {
            self.error = error
        }
    }

    private func uploadAvatar(_ item: PhotosPickerItem) async {
        do {
            let file = try await MediaLoader.image(item, field: "avatar").file
            let updated: Me = try await session.api.upload("me/avatar/", fields: [:], files: [file])
            session.update(updated)
        } catch {
            self.error = error
        }
    }

    private func removeAvatar() async {
        do {
            let updated: Me = try await session.api.send("DELETE", "me/avatar/")
            session.update(updated)
        } catch {
            self.error = error
        }
    }
}

/// 退会。Web と同じく、投稿や写真もすべて削除される。
struct DeleteAccountView: View {
    let me: Me

    @Environment(Session.self) private var session
    @Environment(\.dismiss) private var dismiss
    @State private var confirm = ""
    @State private var agreed = false
    @State private var deleting = false
    @State private var error: Error?

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Text("アカウントを削除すると、Lounge のメッセージ、Blogs の記事 (下書きを含む)、WanderLens のスポットと写真、プロフィールがすべて削除され、元に戻せません。")
                    Toggle("すべて削除されることを理解しました", isOn: $agreed)
                }
                Section {
                    if me.hasPassword {
                        SecureField("パスワード", text: $confirm)
                    } else {
                        TextField("ユーザー名 (\(me.username))", text: $confirm)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                    }
                } footer: {
                    Text(me.hasPassword ? "確認のためパスワードを入力してください。" : "確認のためユーザー名を入力してください。")
                }
                Section {
                    Button("退会する", role: .destructive) { Task { await delete() } }
                        .disabled(!agreed || confirm.isEmpty || deleting)
                }
            }
            .navigationTitle("退会")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("キャンセル") { dismiss() } }
            }
            .errorAlert($error)
        }
    }

    private func delete() async {
        deleting = true
        defer { deleting = false }
        do {
            try await session.deleteAccount(confirm: confirm)
            dismiss()
        } catch {
            self.error = error
        }
    }
}
