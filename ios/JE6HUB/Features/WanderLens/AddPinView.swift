import MapKit
import PhotosUI
import SwiftUI

/// スポットの追加。写真に撮影位置があれば、場所と訪れた日を自動で入れる。
struct AddPinView: View {
    let onAdded: (Pin) -> Void

    @Environment(Session.self) private var session
    @Environment(\.dismiss) private var dismiss
    @State private var items: [PhotosPickerItem] = []
    @State private var photos: [(file: UploadFile, preview: UIImage?)] = []
    @State private var title = ""
    @State private var placeName = ""
    @State private var country = ""
    @State private var description = ""
    @State private var hasVisitedDate = false
    @State private var visitedOn = Date()
    @State private var coordinate: CLLocationCoordinate2D?
    @State private var position: MapCameraPosition = .automatic
    @State private var loadingPhotos = false
    @State private var saving = false
    @State private var error: Error?

    private let maxPhotos = 10

    var body: some View {
        NavigationStack {
            Form {
                Section("写真") {
                    PhotosPicker(selection: $items, maxSelectionCount: maxPhotos, matching: .images) {
                        Label(photos.isEmpty ? "写真を選ぶ" : "写真を選び直す", systemImage: "photo.on.rectangle.angled")
                    }
                    if loadingPhotos { ProgressView() }
                    if !photos.isEmpty {
                        ScrollView(.horizontal) {
                            HStack {
                                ForEach(photos.indices, id: \.self) { index in
                                    if let preview = photos[index].preview {
                                        Image(uiImage: preview).resizable().scaledToFill()
                                            .frame(width: 72, height: 72)
                                            .clipShape(RoundedRectangle(cornerRadius: 8))
                                    }
                                }
                            }
                        }
                    }
                }
                Section("スポット") {
                    TextField("タイトル", text: $title)
                    TextField("場所の名前", text: $placeName)
                    TextField("国", text: $country)
                    Toggle("訪れた日", isOn: $hasVisitedDate)
                    if hasVisitedDate {
                        DatePicker("訪れた日", selection: $visitedOn, displayedComponents: .date)
                    }
                    TextField("説明", text: $description, axis: .vertical).lineLimit(3...8)
                }
                Section {
                    MapReader { proxy in
                        Map(position: $position) {
                            if let coordinate {
                                Marker(title.isEmpty ? "ここ" : title, coordinate: coordinate)
                            }
                        }
                        .onTapGesture { point in
                            if let tapped = proxy.convert(point, from: .local) {
                                setCoordinate(tapped, move: false)
                            }
                        }
                    }
                    .frame(height: 260)
                    .listRowInsets(EdgeInsets())
                } header: {
                    Text("場所")
                } footer: {
                    Text(coordinate == nil ? "地図をタップして場所を選んでください (位置情報付きの写真なら自動で入ります)。"
                                           : "地図をタップすると場所を変えられます。")
                }
            }
            .navigationTitle("スポットを追加")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("キャンセル") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    if saving {
                        ProgressView()
                    } else {
                        Button("追加") { Task { await save() } }
                            .disabled(title.trimmingCharacters(in: .whitespaces).isEmpty || coordinate == nil || loadingPhotos)
                    }
                }
            }
            .onChange(of: items) { _, newItems in Task { await loadPhotos(newItems) } }
            .errorAlert($error)
            .interactiveDismissDisabled(saving)
        }
    }

    private func loadPhotos(_ newItems: [PhotosPickerItem]) async {
        loadingPhotos = true
        defer { loadingPhotos = false }
        var loaded: [(file: UploadFile, preview: UIImage?)] = []
        var firstMetadata: PhotoMetadata?
        for item in newItems {
            do {
                let (file, metadata) = try await MediaLoader.image(item, field: "photos")
                loaded.append((file, UIImage(data: file.data)?.preparingThumbnail(of: CGSize(width: 160, height: 160))))
                if firstMetadata == nil, metadata.latitude != nil { firstMetadata = metadata }
                if !hasVisitedDate, let taken = metadata.takenOn {
                    hasVisitedDate = true
                    visitedOn = taken
                }
            } catch {
                self.error = error
            }
        }
        photos = loaded
        if coordinate == nil, let meta = firstMetadata, let lat = meta.latitude, let lng = meta.longitude {
            setCoordinate(CLLocationCoordinate2D(latitude: lat, longitude: lng), move: true)
        }
    }

    private func setCoordinate(_ value: CLLocationCoordinate2D, move: Bool) {
        coordinate = value
        if move {
            position = .region(MKCoordinateRegion(center: value, span: MKCoordinateSpan(latitudeDelta: 0.05, longitudeDelta: 0.05)))
        }
        // 場所の名前と国が空なら、地名を調べて入れる
        guard placeName.isEmpty || country.isEmpty else { return }
        Task {
            let location = CLLocation(latitude: value.latitude, longitude: value.longitude)
            guard let mark = try? await CLGeocoder().reverseGeocodeLocation(location).first else { return }
            if placeName.isEmpty { placeName = mark.locality ?? mark.name ?? "" }
            if country.isEmpty { country = mark.country ?? "" }
        }
    }

    private func save() async {
        guard let coordinate else { return }
        saving = true
        defer { saving = false }
        var fields = [
            "title": title,
            "place_name": placeName,
            "country": country,
            "description": description,
            "latitude": String(format: "%.6f", coordinate.latitude),
            "longitude": String(format: "%.6f", coordinate.longitude),
        ]
        if hasVisitedDate {
            let formatter = DateFormatter()
            formatter.locale = Locale(identifier: "en_US_POSIX")
            formatter.calendar = Calendar(identifier: .gregorian)
            formatter.dateFormat = "yyyy-MM-dd"
            fields["visited_on"] = formatter.string(from: visitedOn)
        }
        do {
            let pin: Pin = try await session.api.upload("wanderlens/pins/", fields: fields, files: photos.map { $0.file })
            onAdded(pin)
            dismiss()
        } catch {
            self.error = error
        }
    }
}
