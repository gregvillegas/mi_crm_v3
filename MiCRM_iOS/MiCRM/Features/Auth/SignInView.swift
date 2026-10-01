import SwiftUI

struct SignInView: View {
    @Environment(Session.self) private var session

    @State private var username = ""
    @State private var password = ""
    @State private var host = Preferences.serverHost
    @State private var showingServerField = false
    @State private var isWorking = false
    @State private var errorMessage: String?

    @FocusState private var focus: Field?
    private enum Field { case username, password, host }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                masthead
                    .padding(.top, 72)
                    .padding(.bottom, 44)

                fields

                if let errorMessage {
                    Text(errorMessage)
                        .font(TypeScale.caption)
                        .foregroundStyle(Palette.critical)
                        .padding(.top, 14)
                        .transition(.opacity)
                }

                Button(action: submit) {
                    if isWorking {
                        ProgressView().tint(.white)
                    } else {
                        Text("Sign in")
                    }
                }
                .buttonStyle(PrimaryButtonStyle())
                .disabled(isWorking || username.isEmpty || password.isEmpty)
                .padding(.top, 24)

                serverDisclosure
                    .padding(.top, 20)

                Spacer(minLength: 40)
            }
            .padding(.horizontal, 28)
            .frame(maxWidth: 460)
            .frame(maxWidth: .infinity)
        }
        .background(Palette.canvas)
        .animation(.easeInOut(duration: 0.18), value: errorMessage)
        .animation(.easeInOut(duration: 0.2), value: showingServerField)
    }

    // The mark is the only decorative element on the screen; everything below
    // it is working interface.
    private var masthead: some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack(spacing: 3) {
                ForEach(FunnelStageStyle.allCases, id: \.self) { stage in
                    Capsule()
                        .fill(stage.color)
                        .frame(width: 22, height: 5)
                }
            }

            VStack(alignment: .leading, spacing: 6) {
                Text("MiCRM")
                    .font(.system(size: 40, weight: .bold))
                    .tracking(-1.2)
                    .foregroundStyle(Palette.brand)
                Text("Micro Image International")
                    .font(TypeScale.body)
                    .foregroundStyle(Palette.inkMuted)
            }
        }
    }

    private var fields: some View {
        VStack(spacing: 12) {
            LabeledField(
                label: "Username",
                text: $username,
                placeholder: "Your CRM username"
            )
            .plainCapitalization()
            .autocorrectionDisabled()
            .focused($focus, equals: .username)
            .onSubmit { focus = .password }

            LabeledField(
                label: "Password",
                text: $password,
                placeholder: "Password",
                isSecure: true
            )
            .focused($focus, equals: .password)
            .onSubmit(submit)
        }
    }

    private var serverDisclosure: some View {
        VStack(alignment: .leading, spacing: 12) {
            Button {
                showingServerField.toggle()
            } label: {
                HStack(spacing: 6) {
                    Image(systemName: "server.rack")
                        .font(.system(size: 12))
                    Text(showingServerField ? "Hide server settings" : host)
                        .font(TypeScale.caption)
                }
                .foregroundStyle(Palette.inkMuted)
            }

            if showingServerField {
                LabeledField(
                    label: "Server address",
                    text: $host,
                    placeholder: "micrm.microimageph.com"
                )
                .plainCapitalization()
                .autocorrectionDisabled()
                .focused($focus, equals: .host)
                .onChange(of: host) { _, newValue in
                    Task { await session.updateServer(newValue) }
                }
            }
        }
    }

    private func submit() {
        focus = nil
        isWorking = true
        errorMessage = nil
        Task {
            await session.updateServer(host)
            errorMessage = await session.signIn(username: username, password: password)
            isWorking = false
        }
    }
}

/// A labelled text field. The label sits above the control rather than acting
/// as a placeholder, so it stays readable once the field has content.
struct LabeledField: View {
    let label: String
    @Binding var text: String
    var placeholder: String = ""
    var isSecure: Bool = false

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(label)
                .font(TypeScale.caption)
                .foregroundStyle(Palette.inkMuted)

            Group {
                if isSecure {
                    SecureField(placeholder, text: $text)
                } else {
                    TextField(placeholder, text: $text)
                }
            }
            .textFieldStyle(.plain)
            .font(TypeScale.body)
            .foregroundStyle(Palette.ink)
            .padding(.horizontal, 14)
            .frame(height: 48)
            .background(Palette.surface, in: RoundedRectangle(cornerRadius: Metrics.controlRadius))
            .overlay(
                RoundedRectangle(cornerRadius: Metrics.controlRadius)
                    .stroke(Palette.hairline, lineWidth: 1)
            )
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}
