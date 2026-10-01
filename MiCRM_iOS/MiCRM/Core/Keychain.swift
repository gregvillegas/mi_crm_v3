import Foundation
import Security

/// The API token is a long-lived bearer credential, so it belongs in the
/// keychain rather than UserDefaults. The server address is not secret and is
/// kept in UserDefaults alongside it.
enum Keychain {
    private static let service = "com.microimage.crm"
    private static let tokenAccount = "api-token"

    static func saveToken(_ token: String) {
        let data = Data(token.utf8)
        var query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: tokenAccount,
        ]
        SecItemDelete(query as CFDictionary)

        query[kSecValueData as String] = data
        // The token should not sync to other devices or survive a restore onto
        // new hardware.
        query[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        SecItemAdd(query as CFDictionary, nil)
    }

    static func readToken() -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: tokenAccount,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne,
        ]
        var item: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &item) == errSecSuccess,
              let data = item as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }

    static func deleteToken() {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: tokenAccount,
        ]
        SecItemDelete(query as CFDictionary)
    }
}

enum Preferences {
    private static let hostKey = "server.host"
    private static let defaultHost = "micrm.microimageph.com"

    static var serverHost: String {
        get { UserDefaults.standard.string(forKey: hostKey) ?? defaultHost }
        set { UserDefaults.standard.set(newValue, forKey: hostKey) }
    }
}
