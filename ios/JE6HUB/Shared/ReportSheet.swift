import SwiftUI

/// 投稿の通報 (Web の「通報」と同じく、管理者に届く)
struct ReportSheet: View {
    let kind: ReportKind
    let objectID: Int

    @Environment(Session.self) private var session
    @Environment(\.dismiss) private var dismiss
    @State private var reasons: [ReportReason] = []
    @State private var reason = ""
    @State private var detail = ""
    @State private var sending = false
    @State private var sent = false
    @State private var error: Error?

    var body: some View {
        NavigationStack {
            Form {
                if sent {
                    Section {
                        Label("通報を受け付けました。ご協力ありがとうございます。", systemImage: "checkmark.circle")
                    }
                } else {
                    Section("理由") {
                        Picker("理由", selection: $reason) {
                            ForEach(reasons, id: \.value) { Text($0.label).tag($0.value) }
                        }
                        .pickerStyle(.inline)
                        .labelsHidden()
                    }
                    Section("詳しい内容 (任意)") {
                        TextField("", text: $detail, axis: .vertical).lineLimit(3...8)
                    }
                }
            }
            .navigationTitle("通報")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button(sent ? "閉じる" : "キャンセル") { dismiss() }
                }
                if !sent {
                    ToolbarItem(placement: .confirmationAction) {
                        Button("送信") { Task { await send() } }
                            .disabled(reason.isEmpty || sending)
                    }
                }
            }
            .task {
                if let response: ReportReasons = try? await session.api.get("reports/") {
                    reasons = response.reasons
                }
            }
            .errorAlert($error)
        }
    }

    private func send() async {
        sending = true
        defer { sending = false }
        do {
            let _: EmptyResponse = try await session.api.send("POST", "reports/", json: [
                "kind": kind.rawValue, "object_id": objectID, "reason": reason, "detail": detail,
            ])
            sent = true
        } catch {
            self.error = error
        }
    }
}
