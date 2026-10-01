import QuickLook
import SwiftUI

// A handful of SwiftUI modifiers are UIKit-only. Wrapping them here keeps the
// feature code free of `#if os(...)` noise and lets the whole app be
// type-checked against the macOS SDK in CI, where no iOS SDK is installed.

extension View {
    @ViewBuilder
    func inlineNavigationTitle() -> some View {
        #if os(iOS)
        self.navigationBarTitleDisplayMode(.inline)
        #else
        self
        #endif
    }

    @ViewBuilder
    func numericKeyboard() -> some View {
        #if os(iOS)
        self.keyboardType(.numberPad)
        #else
        self
        #endif
    }

    @ViewBuilder
    func emailKeyboard() -> some View {
        #if os(iOS)
        self.keyboardType(.emailAddress).textInputAutocapitalization(.never)
        #else
        self
        #endif
    }

    @ViewBuilder
    func phoneKeyboard() -> some View {
        #if os(iOS)
        self.keyboardType(.phonePad)
        #else
        self
        #endif
    }

    @ViewBuilder
    func plainCapitalization() -> some View {
        #if os(iOS)
        self.textInputAutocapitalization(.never)
        #else
        self
        #endif
    }
}

extension View {
    /// Presents a downloaded PDF (a quotation) in the system previewer, with a
    /// share action for free. Binding is cleared by QuickLook on dismiss.
    func quickLook(url: Binding<URL?>) -> some View {
        quickLookPreview(url)
    }
}
