import SwiftUI

/// Second factor. Reached only when the server answers the password step with
/// an MFA challenge.
struct VerifyCodeView: View {
    @Environment(Session.self) private var session

    let username: String

    @State private var code = ""
    @State private var isWorking = false
    @State private var errorMessage: String?
    @FocusState private var codeFocused: Bool

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                Image(systemName: "lock.shield")
                    .font(.system(size: 30, weight: .light))
                    .foregroundStyle(Palette.brand)
                    .padding(.top, 84)
                    .padding(.bottom, 22)

                Text("Two-step verification")
                    .font(.system(size: 28, weight: .bold))
                    .tracking(-0.6)
                    .foregroundStyle(Palette.ink)

                Text("Enter the 6-digit code from your authenticator app for \(username). A recovery code works too.")
                    .font(TypeScale.body)
                    .foregroundStyle(Palette.inkMuted)
                    .padding(.top, 8)
                    .fixedSize(horizontal: false, vertical: true)

                codeField
                    .padding(.top, 28)

                if let errorMessage {
                    Text(errorMessage)
                        .font(TypeScale.caption)
                        .foregroundStyle(Palette.critical)
                        .padding(.top, 12)
                }

                Button(action: submit) {
                    if isWorking {
                        ProgressView().tint(.white)
                    } else {
                        Text("Verify")
                    }
                }
                .buttonStyle(PrimaryButtonStyle())
                .disabled(isWorking || code.count < 6)
                .padding(.top, 22)

                Button("Use a different account") {
                    session.cancelCodeEntry()
                }
                .font(TypeScale.caption)
                .foregroundStyle(Palette.inkMuted)
                .frame(maxWidth: .infinity)
                .padding(.top, 18)

                Spacer(minLength: 40)
            }
            .padding(.horizontal, 28)
            .frame(maxWidth: 460)
            .frame(maxWidth: .infinity)
        }
        .background(Palette.canvas)
        .onAppear { codeFocused = true }
        .animation(.easeInOut(duration: 0.18), value: errorMessage)
    }

    private var codeField: some View {
        TextField("000000", text: $code)
            .textFieldStyle(.plain)
            .font(.system(size: 30, weight: .semibold, design: .monospaced))
            .tracking(8)
            .multilineTextAlignment(.center)
            .foregroundStyle(Palette.ink)
            .numericKeyboard()
            .focused($codeFocused)
            .frame(height: 62)
            .background(Palette.surface, in: RoundedRectangle(cornerRadius: Metrics.controlRadius))
            .overlay(
                RoundedRectangle(cornerRadius: Metrics.controlRadius)
                    .stroke(errorMessage == nil ? Palette.hairline : Palette.critical, lineWidth: 1)
            )
            .onChange(of: code) { _, newValue in
                // Recovery codes are longer than a TOTP, so allow up to 10.
                let digits = newValue.filter { $0.isNumber || $0.isLetter }
                if digits != newValue { code = String(digits.prefix(10)) }
                else if newValue.count > 10 { code = String(newValue.prefix(10)) }
                errorMessage = nil
            }
    }

    private func submit() {
        codeFocused = false
        isWorking = true
        errorMessage = nil
        Task {
            errorMessage = await session.submitCode(code)
            isWorking = false
        }
    }
}
