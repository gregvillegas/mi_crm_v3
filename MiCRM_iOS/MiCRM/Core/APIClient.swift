import Foundation

enum APIError: LocalizedError {
    case notConfigured
    case unauthorized
    case forbidden(String)
    case notFound
    case server(status: Int, detail: String?)
    case transport(Error)
    case decoding(Error)

    var errorDescription: String? {
        switch self {
        case .notConfigured:
            return "Set the server address before signing in."
        case .unauthorized:
            return "Your session has expired. Sign in again."
        case .forbidden(let detail):
            return detail
        case .notFound:
            return "That record is no longer available."
        case .server(let status, let detail):
            return detail ?? "The server returned an error (\(status))."
        case .transport:
            return "Can't reach the server. Check your connection and the server address."
        case .decoding:
            return "The server sent a response the app could not read."
        }
    }
}

/// Talks to /api/v1. One instance per app, holding the token and base URL.
actor APIClient {
    static let shared = APIClient()

    private var baseURL: URL?
    private var token: String?

    private let session: URLSession
    private let decoder: JSONDecoder
    private let encoder: JSONEncoder

    init(session: URLSession = .shared) {
        self.session = session

        decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .custom { decoder in
            let raw = try decoder.singleValueContainer().decode(String.self)
            if let date = DateParsing.parse(raw) { return date }
            throw DecodingError.dataCorrupted(
                .init(codingPath: decoder.codingPath, debugDescription: "Unrecognised date: \(raw)")
            )
        }

        encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
    }

    // MARK: - Configuration

    func configure(host: String) {
        baseURL = Self.normalizedBaseURL(host: host)
    }

    /// Accepts "crm.example.com", "10.20.20.2:8001" or a full URL, and
    /// normalises it to `<scheme>://<host>/api/v1/`.
    ///
    /// Static and pure so the normalisation rules can be tested directly.
    static func normalizedBaseURL(host: String) -> URL? {
        var text = host.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return nil }

        if !text.lowercased().hasPrefix("http") {
            // Only LAN/dev servers run plain http; everything else is the public
            // site and stays on TLS, even when a port is given.
            text = isLocalHost(text) ? "http://\(text)" : "https://\(text)"
        }
        while text.hasSuffix("/") { text.removeLast() }
        if !text.hasSuffix("/api/v1") { text += "/api/v1" }
        return URL(string: text + "/")
    }

    /// Mirrors the Android client's rule: localhost, `.local` and the private
    /// IPv4 ranges are the only hosts allowed to fall back to cleartext.
    static func isLocalHost(_ host: String) -> Bool {
        let name = String(host.prefix { $0 != "/" && $0 != ":" }).lowercased()
        if name == "localhost" || name.hasSuffix(".local") { return true }
        if name.hasPrefix("10.") || name.hasPrefix("127.") || name.hasPrefix("192.168.") {
            return true
        }
        return name.range(of: #"^172\.(1[6-9]|2\d|3[01])\."#, options: .regularExpression) != nil
    }

    func setToken(_ value: String?) { token = value }
    var isAuthenticated: Bool { token != nil }

    // MARK: - Request plumbing

    private func makeRequest(
        _ path: String,
        method: String,
        query: [String: String?] = [:],
        body: Data? = nil,
        authenticated: Bool = true
    ) throws -> URLRequest {
        guard let baseURL else { throw APIError.notConfigured }

        var components = URLComponents(
            url: baseURL.appendingPathComponent(path),
            resolvingAgainstBaseURL: false
        )
        let items = query.compactMap { key, value -> URLQueryItem? in
            guard let value, !value.isEmpty else { return nil }
            return URLQueryItem(name: key, value: value)
        }
        if !items.isEmpty { components?.queryItems = items }

        guard let url = components?.url else { throw APIError.notConfigured }

        var request = URLRequest(url: url)
        request.httpMethod = method
        request.timeoutInterval = 30
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if body != nil {
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = body
        }
        if authenticated, let token {
            request.setValue("Token \(token)", forHTTPHeaderField: "Authorization")
        }
        return request
    }

    private func perform(_ request: URLRequest) async throws -> Data {
        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: request)
        } catch {
            throw APIError.transport(error)
        }

        guard let http = response as? HTTPURLResponse else {
            throw APIError.server(status: -1, detail: nil)
        }

        switch http.statusCode {
        case 200...299:
            return data
        case 401:
            throw APIError.unauthorized
        case 403:
            throw APIError.forbidden(Self.detail(from: data) ?? "You don't have access to that.")
        case 404:
            throw APIError.notFound
        default:
            throw APIError.server(status: http.statusCode, detail: Self.detail(from: data))
        }
    }

    private static func detail(from data: Data) -> String? {
        guard let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return nil }
        if let detail = object["detail"] as? String { return detail }
        // DRF field errors: {"email": ["Enter a valid email address."]}
        for value in object.values {
            if let list = value as? [String], let first = list.first { return first }
        }
        return nil
    }

    private func decode<T: Decodable>(_ type: T.Type, from data: Data) throws -> T {
        do {
            return try decoder.decode(T.self, from: data)
        } catch {
            throw APIError.decoding(error)
        }
    }

    private func get<T: Decodable>(_ path: String, query: [String: String?] = [:]) async throws -> T {
        let data = try await perform(try makeRequest(path, method: "GET", query: query))
        return try decode(T.self, from: data)
    }

    @discardableResult
    private func post<Body: Encodable, T: Decodable>(
        _ path: String, body: Body, authenticated: Bool = true
    ) async throws -> T {
        let payload = try encoder.encode(body)
        let data = try await perform(
            try makeRequest(path, method: "POST", body: payload, authenticated: authenticated)
        )
        return try decode(T.self, from: data)
    }

    @discardableResult
    private func postEmpty<T: Decodable>(_ path: String) async throws -> T {
        let data = try await perform(try makeRequest(path, method: "POST", body: Data("{}".utf8)))
        return try decode(T.self, from: data)
    }

    // MARK: - Auth

    struct Credentials: Encodable { let username: String; let password: String }
    struct MFAVerification: Encodable { let mfaToken: String; let code: String }

    func signIn(username: String, password: String) async throws -> AuthResponse {
        try await post(
            "api-token-auth/",
            body: Credentials(username: username, password: password),
            authenticated: false
        )
    }

    func verifyMFA(mfaToken: String, code: String) async throws -> AuthResponse {
        try await post(
            "api-token-auth/mfa/",
            body: MFAVerification(mfaToken: mfaToken, code: code),
            authenticated: false
        )
    }

    func signOut() async {
        // Best effort: the local token is cleared regardless.
        _ = try? await perform(try makeRequest("logout/", method: "POST", body: Data("{}".utf8)))
        token = nil
    }

    func currentUser() async throws -> CurrentUser { try await get("users/me/") }

    // MARK: - Dashboard

    func dashboard() async throws -> DashboardSummary { try await get("dashboard/") }

    // MARK: - Customers

    func customers(search: String? = nil, mineOnly: Bool = false) async throws -> [CustomerSummary] {
        try await get(mineOnly ? "customers/mine/" : "customers/", query: ["search": search])
    }

    func customer(id: Int) async throws -> CustomerDetail { try await get("customers/\(id)/") }

    func customerChoices() async throws -> CustomerChoices { try await get("customers/choices/") }

    // MARK: - Customer create-requests

    func myCustomerRequests() async throws -> [CustomerRequest] {
        try await get("customer-requests/mine/")
    }

    func pendingCustomerRequests() async throws -> [CustomerRequest] {
        try await get("customer-requests/pending/")
    }

    func submitCustomerRequest(_ request: NewCustomerRequest) async throws -> CustomerRequest {
        try await post("customer-requests/", body: request)
    }

    func decideCustomerRequest(id: Int, approve: Bool, note: String = "") async throws {
        struct Note: Encodable { let note: String }
        let _: APIMessage = try await post(
            "customer-requests/\(id)/\(approve ? "approve" : "reject")/",
            body: Note(note: note)
        )
    }

    // MARK: - Funnel

    func funnel(stage: String? = nil) async throws -> [FunnelEntry] {
        try await get("funnel/", query: ["stage": stage])
    }

    // MARK: - Proposals

    func proposals(search: String? = nil, approvalStatus: String? = nil) async throws -> [ProposalSummary] {
        try await get("proposals/", query: ["search": search, "approval_status": approvalStatus])
    }

    func proposal(id: Int) async throws -> ProposalDetail { try await get("proposals/\(id)/") }

    func pendingApprovals() async throws -> [PendingApproval] {
        try await get("proposals/pending_approvals/")
    }

    func decideProposal(id: Int, approve: Bool, comment: String) async throws {
        struct Envelope: Decodable { let detail: String? }
        let _: Envelope = try await post(
            "proposals/\(id)/\(approve ? "approve" : "reject")/",
            body: ApprovalDecision(comment: comment)
        )
    }

    /// Downloads the quotation to a temporary file and returns its location,
    /// ready to hand to a share sheet or QuickLook.
    func downloadProposalPDF(id: Int, number: String) async throws -> URL {
        let request = try makeRequest("proposals/\(id)/pdf/", method: "GET")
        let data = try await perform(request)
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("\(number).pdf")
        try data.write(to: url, options: .atomic)
        return url
    }

    // MARK: - Activities

    func activities(
        status: String? = nil, customerId: Int? = nil, upcomingOnly: Bool = false
    ) async throws -> [SalesActivity] {
        try await get("activities/", query: [
            "status": status,
            "customer": customerId.map(String.init),
            "upcoming": upcomingOnly ? "true" : nil,
        ])
    }

    func activityTypes() async throws -> [ActivityType] { try await get("activity-types/") }

    func createActivity(_ activity: NewActivity) async throws -> SalesActivity {
        try await post("activities/", body: activity)
    }

    func completeActivity(id: Int, notes: String?) async throws -> SalesActivity {
        try await post("activities/\(id)/complete/", body: ActivityCompletion(notes: notes))
    }

    // MARK: - Campaigns

    func campaigns() async throws -> [CampaignSummary] { try await get("campaigns/") }
}

// MARK: - Dates

enum DateParsing {
    private static let withFraction: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f
    }()

    private static let plain: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime]
        return f
    }()

    private static let dateOnly: DateFormatter = {
        let f = DateFormatter()
        f.calendar = Calendar(identifier: .iso8601)
        f.locale = Locale(identifier: "en_US_POSIX")
        f.dateFormat = "yyyy-MM-dd"
        return f
    }()

    static func parse(_ raw: String) -> Date? {
        withFraction.date(from: raw) ?? plain.date(from: raw) ?? dateOnly.date(from: raw)
    }
}
