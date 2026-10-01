import Foundation
import Observation

/// Owns the signed-in state for the whole app.
@MainActor
@Observable
final class Session {
    enum Phase: Equatable {
        case loading
        case signedOut
        /// Password accepted; the server is waiting for an authenticator code.
        case awaitingCode(mfaToken: String, username: String)
        case signedIn
    }

    private(set) var phase: Phase = .loading
    private(set) var user: CurrentUser?
    var serverHost: String = Preferences.serverHost

    private let api = APIClient.shared

    // MARK: - Startup

    func restore() async {
        await api.configure(host: serverHost)

        guard let token = Keychain.readToken() else {
            phase = .signedOut
            return
        }

        await api.setToken(token)
        do {
            user = try await api.currentUser()
            phase = .signedIn
        } catch {
            // A stored token that no longer works is not an error worth showing;
            // just return the person to the sign-in screen.
            Keychain.deleteToken()
            await api.setToken(nil)
            phase = .signedOut
        }
    }

    // MARK: - Sign in

    func updateServer(_ host: String) async {
        serverHost = host
        Preferences.serverHost = host
        await api.configure(host: host)
    }

    /// Returns nil on success, or a message to show the user.
    func signIn(username: String, password: String) async -> String? {
        await api.configure(host: serverHost)
        do {
            let response = try await api.signIn(username: username, password: password)

            if response.mfaRequired == true, let mfaToken = response.mfaToken {
                phase = .awaitingCode(mfaToken: mfaToken, username: username)
                return nil
            }
            guard let token = response.token else {
                return response.detail ?? "The server did not return a sign-in token."
            }
            try await finish(with: token)
            return nil
        } catch let error as APIError {
            if case .forbidden(let detail) = error { return detail }
            if case .server(let status, let detail) = error, status == 400 {
                return detail ?? "That username and password did not match."
            }
            return error.localizedDescription
        } catch {
            return error.localizedDescription
        }
    }

    func submitCode(_ code: String) async -> String? {
        guard case .awaitingCode(let mfaToken, _) = phase else { return "Start the sign-in again." }
        do {
            let response = try await api.verifyMFA(mfaToken: mfaToken, code: code)
            guard let token = response.token else {
                return response.detail ?? "That code was not accepted."
            }
            try await finish(with: token)
            return nil
        } catch let error as APIError {
            if case .server(_, let detail) = error, let detail { return detail }
            if case .unauthorized = error {
                return "That code is not valid. Check your authenticator app and try again."
            }
            return error.localizedDescription
        } catch {
            return error.localizedDescription
        }
    }

    func cancelCodeEntry() {
        phase = .signedOut
    }

    private func finish(with token: String) async throws {
        Keychain.saveToken(token)
        await api.setToken(token)
        user = try await api.currentUser()
        phase = .signedIn
    }

    // MARK: - Sign out

    func signOut() async {
        await api.signOut()
        Keychain.deleteToken()
        user = nil
        phase = .signedOut
    }

    /// Called when any screen sees a 401 — the token was revoked server-side.
    func handleExpiredSession() async {
        Keychain.deleteToken()
        await api.setToken(nil)
        user = nil
        phase = .signedOut
    }

    // MARK: - Role helpers

    var canReviewApprovals: Bool {
        guard let role = user?.role else { return false }
        return !["salesperson"].contains(role)
    }

    var isSalesperson: Bool { user?.role == "salesperson" }
}
