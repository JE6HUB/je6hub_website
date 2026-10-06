import SwiftUI
import WebKit

/// 記事の本文 (サーバーでサニタイズ済みの HTML) を表示する。高さは中身に合わせて伸びる。
/// 本文中のリンクは Safari などで開く。
struct HTMLView: UIViewRepresentable {
    let html: String
    @Binding var height: CGFloat

    func makeCoordinator() -> Coordinator { Coordinator(height: $height) }

    func makeUIView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        config.defaultWebpagePreferences.allowsContentJavaScript = false
        let webView = WKWebView(frame: .zero, configuration: config)
        webView.isOpaque = false
        webView.backgroundColor = .clear
        webView.scrollView.isScrollEnabled = false
        webView.navigationDelegate = context.coordinator
        return webView
    }

    func updateUIView(_ webView: WKWebView, context: Context) {
        guard context.coordinator.loadedHTML != html else { return }
        context.coordinator.loadedHTML = html
        webView.loadHTMLString(Self.document(html), baseURL: AppConfig.baseURL)
    }

    static func document(_ body: String) -> String {
        """
        <!DOCTYPE html><html><head><meta charset="utf-8">
        <meta name="viewport" content="width=device-width,initial-scale=1">
        <style>
        :root { color-scheme: light dark; }
        body { margin: 0; font: -apple-system-body; line-height: 1.75; word-wrap: break-word; }
        img, video, iframe { max-width: 100%; height: auto; border-radius: 12px; }
        pre { white-space: pre-wrap; background: rgba(127,127,127,.12); padding: 12px; border-radius: 10px; font-size: 13px; }
        code { font-family: ui-monospace, Menlo, monospace; }
        blockquote { margin: 0; padding-left: 14px; border-left: 3px solid rgba(127,127,127,.4); color: gray; }
        a { color: #2997ff; }
        h1, h2, h3 { line-height: 1.35; }
        hr { border: 0; border-top: 1px solid rgba(127,127,127,.3); margin: 28px 0; }
        table { border-collapse: collapse; } td, th { border: 1px solid rgba(127,127,127,.3); padding: 6px; }
        </style></head><body>\(body)</body></html>
        """
    }

    final class Coordinator: NSObject, WKNavigationDelegate {
        var loadedHTML: String?
        let height: Binding<CGFloat>

        init(height: Binding<CGFloat>) { self.height = height }

        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            // スクリプトは無効にしているので、レイアウト後の contentSize から高さを取る
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
                self.height.wrappedValue = webView.scrollView.contentSize.height
            }
        }

        func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction,
                     decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
            if action.navigationType == .linkActivated, let url = action.request.url {
                UIApplication.shared.open(url)
                decisionHandler(.cancel)
                return
            }
            decisionHandler(.allow)
        }
    }
}
