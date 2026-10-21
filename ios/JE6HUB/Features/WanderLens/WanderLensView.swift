import MapKit
import SwiftUI

/// みんなの旅の地図。ピンをタップするとスポットの詳細へ。
struct WanderLensView: View {
    @Environment(Session.self) private var session
    @State private var pins: [Pin] = []
    @State private var onlyMine = false
    @State private var position: MapCameraPosition = .automatic
    @State private var selected: Pin?
    @State private var showAdd = false
    @State private var showLogin = false
    @State private var error: Error?

    private var visiblePins: [Pin] {
        guard onlyMine, let me = session.me else { return pins }
        return pins.filter { $0.owner.username == me.username }
    }

    var body: some View {
        Map(position: $position) {
            ForEach(visiblePins) { pin in
                Annotation(pin.title, coordinate: CLLocationCoordinate2D(latitude: pin.latitude, longitude: pin.longitude)) {
                    Button { selected = pin } label: { PinMarker(pin: pin) }
                        .buttonStyle(.plain)
                }
            }
        }
        .mapStyle(.standard(elevation: .realistic, pointsOfInterest: .excludingAll))
        .safeAreaInset(edge: .bottom) {
            if !visiblePins.isEmpty {
                recentStrip
            }
        }
        .navigationTitle("WanderLens")
        .navigationBarTitleDisplayMode(.inline)
        .navigationDestination(item: $selected) { pin in PinDetailView(pinID: pin.id) }
        .toolbar {
            ToolbarItem(placement: .topBarLeading) {
                if session.isLoggedIn {
                    Picker("表示", selection: $onlyMine) {
                        Text("みんな").tag(false)
                        Text("自分").tag(true)
                    }
                    .pickerStyle(.segmented)
                    .fixedSize()
                }
            }
            ToolbarItem(placement: .primaryAction) {
                Button {
                    if session.isLoggedIn { showAdd = true } else { showLogin = true }
                } label: { Image(systemName: "plus") }
                .accessibilityLabel("スポットを追加")
            }
        }
        .sheet(isPresented: $showAdd) {
            AddPinView { pin in
                pins.insert(pin, at: 0)
                position = .region(MKCoordinateRegion(
                    center: CLLocationCoordinate2D(latitude: pin.latitude, longitude: pin.longitude),
                    span: MKCoordinateSpan(latitudeDelta: 0.5, longitudeDelta: 0.5)))
            }
        }
        .sheet(isPresented: $showLogin) { LoginView() }
        .task { await load() }
        .onChange(of: onlyMine) { _, _ in position = .automatic }
        .errorAlert($error)
    }

    private var recentStrip: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 10) {
                ForEach(visiblePins.prefix(12)) { pin in
                    Button { selected = pin } label: {
                        VStack(alignment: .leading, spacing: 4) {
                            RemoteImage(url: pin.photos.first?.thumbUrl ?? "")
                                .frame(width: 120, height: 80)
                                .clipShape(RoundedRectangle(cornerRadius: 8))
                            Text(pin.title).font(.caption.weight(.semibold)).lineLimit(1)
                            Text(pin.owner.name).font(.caption2).foregroundStyle(.secondary).lineLimit(1)
                        }
                        .frame(width: 120)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal)
            .padding(.vertical, 10)
        }
        .background(.ultraThinMaterial)
    }

    private func load() async {
        do {
            let response: PinsResponse = try await session.api.get("wanderlens/pins/")
            pins = response.results
        } catch is CancellationError {
        } catch {
            self.error = error
        }
    }
}

struct PinMarker: View {
    let pin: Pin

    var body: some View {
        Group {
            if let thumb = pin.photos.first?.thumbUrl {
                RemoteImage(url: thumb)
                    .frame(width: 40, height: 40)
                    .clipShape(RoundedRectangle(cornerRadius: 8))
                    .overlay(RoundedRectangle(cornerRadius: 8).stroke(.white, lineWidth: 2))
            } else {
                Image(systemName: "mappin.circle.fill")
                    .font(.title)
                    .foregroundStyle(.white, Color.accentColor)
            }
        }
        .shadow(radius: 3)
    }
}
