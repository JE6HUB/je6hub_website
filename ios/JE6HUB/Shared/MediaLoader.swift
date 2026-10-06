import CoreTransferable
import ImageIO
import PhotosUI
import SwiftUI
import UniformTypeIdentifiers

/// 写真から読み取った撮影位置と撮影日 (WanderLens の場所の初期値に使う)
struct PhotoMetadata {
    var latitude: Double?
    var longitude: Double?
    var takenOn: Date?
}

/// 写真ライブラリで選んだ画像・動画を、サーバーに送れる形 (JPEG / MP4・MOV) にする。
/// iPhone の写真は HEIC のことが多いが、サーバーは JPEG / PNG / WebP しか受け付けないので JPEG に変換する。
/// (撮影位置などのメタデータは送らない。位置が必要なときは PhotoMetadata で読み取って別に送る)
enum MediaLoader {
    struct LoadError: LocalizedError {
        var errorDescription: String? { "写真・動画を読み込めませんでした。" }
    }

    static func upload(_ item: PhotosPickerItem, field: String) async throws -> UploadFile {
        if item.supportedContentTypes.contains(where: { $0.conforms(to: .movie) }) {
            guard let movie = try await item.loadTransferable(type: Movie.self) else { throw LoadError() }
            defer { try? FileManager.default.removeItem(at: movie.url) }
            let data = try Data(contentsOf: movie.url)
            let isMP4 = movie.url.pathExtension.lowercased() == "mp4"
            return UploadFile(field: field, filename: isMP4 ? "video.mp4" : "video.mov",
                              mimeType: isMP4 ? "video/mp4" : "video/quicktime", data: data)
        }
        return try await image(item, field: field).file
    }

    static func image(_ item: PhotosPickerItem, field: String) async throws -> (file: UploadFile, metadata: PhotoMetadata) {
        guard let data = try await item.loadTransferable(type: Data.self) else { throw LoadError() }
        let metadata = readMetadata(data)
        guard let image = UIImage(data: data), let jpeg = resized(image, maxSide: 3000).jpegData(compressionQuality: 0.88) else {
            throw LoadError()
        }
        return (UploadFile(field: field, filename: "photo.jpg", mimeType: "image/jpeg", data: jpeg), metadata)
    }

    static func readMetadata(_ data: Data) -> PhotoMetadata {
        var result = PhotoMetadata()
        guard let source = CGImageSourceCreateWithData(data as CFData, nil),
              let properties = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any] else {
            return result
        }
        if let gps = properties[kCGImagePropertyGPSDictionary] as? [CFString: Any],
           let lat = gps[kCGImagePropertyGPSLatitude] as? Double,
           let lng = gps[kCGImagePropertyGPSLongitude] as? Double {
            let latRef = gps[kCGImagePropertyGPSLatitudeRef] as? String ?? "N"
            let lngRef = gps[kCGImagePropertyGPSLongitudeRef] as? String ?? "E"
            result.latitude = latRef == "S" ? -lat : lat
            result.longitude = lngRef == "W" ? -lng : lng
        }
        if let exif = properties[kCGImagePropertyExifDictionary] as? [CFString: Any],
           let original = exif[kCGImagePropertyExifDateTimeOriginal] as? String {
            let formatter = DateFormatter()
            formatter.locale = Locale(identifier: "en_US_POSIX")
            formatter.dateFormat = "yyyy:MM:dd HH:mm:ss"
            result.takenOn = formatter.date(from: original)
        }
        return result
    }

    private static func resized(_ image: UIImage, maxSide: CGFloat) -> UIImage {
        let side = max(image.size.width, image.size.height)
        guard side > maxSide else { return image }
        let scale = maxSide / side
        let size = CGSize(width: image.size.width * scale, height: image.size.height * scale)
        let format = UIGraphicsImageRendererFormat.default()
        format.scale = 1
        return UIGraphicsImageRenderer(size: size, format: format).image { _ in
            image.draw(in: CGRect(origin: .zero, size: size))
        }
    }
}

/// 写真ライブラリの動画を一時ファイルとして受け取る
struct Movie: Transferable {
    let url: URL

    static var transferRepresentation: some TransferRepresentation {
        FileRepresentation(contentType: .movie) { movie in
            SentTransferredFile(movie.url)
        } importing: { received in
            let copy = FileManager.default.temporaryDirectory
                .appendingPathComponent(UUID().uuidString)
                .appendingPathExtension(received.file.pathExtension)
            try FileManager.default.copyItem(at: received.file, to: copy)
            return Movie(url: copy)
        }
    }
}
