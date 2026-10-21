import MapKit
import SwiftUI

struct PinDetailView: View {
    let pinID: Int

    @Environment(Session.self) private var session
    @Environment(\.dismiss) private var dismiss
    @State private var pin: Pin?
    @State private var comments: [PinComment] = []
    @State private var loadError: Error?
    @State private var error: Error?
    @State private var text = ""
    @State private var guestName = ""
    @State private var sending = false
    @State private var confirmDelete = false
    @State private var report: (kind: ReportKind, id: Int)?

    private var isMine: Bool { pin?.owner.username != nil && pin?.owner.username == session.me?.username }

    var body: some View {
        Group {
            if let pin {
                content(pin)
            } else if let loadError {
                ErrorView(error: loadError) { await load() }
            } else {
                ProgressView()
            }
        }
        .navigationTitle(pin?.title ?? "")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            if let pin {
                ToolbarItem(placement: .primaryAction) {
                    Menu {
                        if isMine {
                            Button(role: .destructive) { confirmDelete = true } label: { Label("削除", systemImage: "trash") }
                        } else if session.isLoggedIn {
                            Button(role: .destructive) { report = (.pin, pin.id) } label: {
                                Label("スポットを通報", systemImage: "exclamationmark.bubble")
                            }
                        }
                    } label: { Image(systemName: "ellipsis.circle") }
                }
            }
        }
        .confirmationDialog("このスポットを写真ごと削除しますか？", isPresented: $confirmDelete, titleVisibility: .visible) {
            Button("削除", role: .destructive) { Task { await delete() } }
        }
        .sheet(isPresented: Binding(get: { report != nil }, set: { if !$0 { report = nil } })) {
            if let report { ReportSheet(kind: report.kind, objectID: report.id) }
        }
        .task { await load() }
        .errorAlert($error)
    }

    private func content(_ pin: Pin) -> some View {
        let coordinate = CLLocationCoordinate2D(latitude: pin.latitude, longitude: pin.longitude)
        return ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                if !pin.photos.isEmpty {
                    TabView {
                        ForEach(pin.photos) { photo in
                            RemoteImage(url: photo.url, contentMode: .fit)
                        }
                    }
                    .tabViewStyle(.page)
                    .frame(height: 300)
                    .background(Color.black)
                }
                VStack(alignment: .leading, spacing: 8) {
                    Text(pin.title).font(.title2.bold())
                    let place = [pin.placeName, pin.country].filter { !$0.isEmpty }.joined(separator: ", ")
                    if !place.isEmpty {
                        Label(place, systemImage: "mappin.and.ellipse").foregroundStyle(.secondary)
                    }
                    if let visited = pin.visitedOn {
                        Label(visited, systemImage: "calendar").foregroundStyle(.secondary)
                    }
                    if let username = pin.owner.username {
                        NavigationLink(value: Route.user(username)) { AuthorLabel(user: pin.owner) }
                            .buttonStyle(.plain)
                    }
                    if !pin.description.isEmpty {
                        Text(pin.description).padding(.top, 4)
                    }
                    Map(initialPosition: .region(MKCoordinateRegion(
                        center: coordinate, span: MKCoordinateSpan(latitudeDelta: 0.05, longitudeDelta: 0.05)))) {
                        Marker(pin.title, coordinate: coordinate)
                    }
                    .frame(height: 180)
                    .clipShape(RoundedRectangle(cornerRadius: 12))
                    .allowsHitTesting(false)

                    Divider().padding(.vertical, 6)
                    commentsSection(pin)
                }
                .padding(.horizontal)
            }
            .padding(.bottom, 32)
        }
    }

    private func commentsSection(_ pin: Pin) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("コメント").font(.headline)
            if comments.isEmpty {
                Text("まだコメントはありません。").font(.subheadline).foregroundStyle(.secondary)
            }
            ForEach(comments) { comment in
                VStack(alignment: .leading, spacing: 3) {
                    HStack {
                        Text(comment.authorName).font(.subheadline.weight(.semibold))
                        Text(comment.createdAt.relative).font(.caption).foregroundStyle(.secondary)
                    }
                    Text(comment.text).textSelection(.enabled)
                }
                .contextMenu {
                    if session.isLoggedIn {
                        Button(role: .destructive) { report = (.pinComment, comment.id) } label: {
                            Label("通報", systemImage: "exclamationmark.bubble")
                        }
                    }
                }
            }
            if !session.isLoggedIn {
                TextField("お名前", text: $guestName).textFieldStyle(.roundedBorder)
            }
            TextField("コメントを書く", text: $text, axis: .vertical)
                .lineLimit(2...5)
                .textFieldStyle(.roundedBorder)
            Button("送信") { Task { await send() } }
                .buttonStyle(.borderedProminent)
                .disabled(text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || sending)
        }
    }

    private func load() async {
        do {
            pin = try await session.api.get("wanderlens/pins/\(pinID)/")
            let response: PinCommentsResponse = try await session.api.get("wanderlens/pins/\(pinID)/comments/")
            comments = response.results
            loadError = nil
        } catch is CancellationError {
        } catch {
            loadError = error
        }
    }

    private func send() async {
        sending = true
        defer { sending = false }
        var body: [String: Any] = ["text": text]
        if !session.isLoggedIn { body["author_name"] = guestName }
        do {
            let comment: PinComment = try await session.api.send("POST", "wanderlens/pins/\(pinID)/comments/", json: body)
            comments.append(comment)
            text = ""
        } catch {
            self.error = error
        }
    }

    private func delete() async {
        do {
            let _: EmptyResponse = try await session.api.send("DELETE", "wanderlens/pins/\(pinID)/")
            dismiss()
        } catch {
            self.error = error
        }
    }
}
