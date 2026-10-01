import Foundation

// Decodes the fixtures dumped by crm_project.tests_api.ContractFixtureTests
// using the app's own Codable models. If a Django serializer changes shape,
// this fails here rather than at runtime on a salesperson's phone.

func runContractChecks(decoder: JSONDecoder) -> Int {
    let directory = "/tmp/micrm-contract"
    guard FileManager.default.fileExists(atPath: directory) else {
        print("\nContract fixtures not found — run:")
        print("  MICRM_DUMP_CONTRACT=1 python manage.py test crm_project.tests_api.ContractFixtureTests")
        return 0
    }

    var failed = 0

    func decodeFixture<T: Decodable>(_ name: String, as type: T.Type, describe: (T) -> String) {
        let path = "\(directory)/\(name).json"
        guard let data = FileManager.default.contents(atPath: path) else {
            print("  FAIL  \(name): fixture missing")
            failed += 1
            return
        }
        do {
            let value = try decoder.decode(T.self, from: data)
            print("  ok    \(name)  ->  \(describe(value))")
        } catch {
            print("  FAIL  \(name): \(error)")
            failed += 1
        }
    }

    print("\nDecoding real API responses with the app's models")

    decodeFixture("dashboard", as: DashboardSummary.self) {
        "\($0.funnel.stages.count) stages, pipeline \(Format.compactCurrency($0.funnel.totalValue))"
    }
    decodeFixture("me", as: CurrentUser.self) { $0.displayName }
    decodeFixture("customers", as: [CustomerSummary].self) { "\($0.count) customer(s)" }
    decodeFixture("customer_detail", as: CustomerDetail.self) { $0.companyName }
    decodeFixture("customer_choices", as: CustomerChoices.self) {
        "\($0.industries.count) industries, \($0.territories.count) territories"
    }
    decodeFixture("customer_requests_mine", as: [CustomerRequest].self) { "\($0.count) request(s)" }
    decodeFixture("funnel", as: [FunnelEntry].self) {
        "\($0.count) entry(s), first stage \($0.first?.style.shortLabel ?? "n/a")"
    }
    decodeFixture("proposals", as: [ProposalSummary].self) { "\($0.count) proposal(s)" }
    decodeFixture("proposal_detail", as: ProposalDetail.self) {
        "\($0.proposalNumber), \($0.approvalSteps.count) approval step(s)"
    }
    decodeFixture("pending_approvals", as: [PendingApproval].self) { "\($0.count) waiting" }
    decodeFixture("activities", as: [SalesActivity].self) { "\($0.count) activity(s)" }
    decodeFixture("activity_types", as: [ActivityType].self) {
        $0.map(\.name).joined(separator: ", ")
    }
    decodeFixture("campaigns", as: [CampaignSummary].self) { "\($0.count) campaign(s)" }
    decodeFixture("auth_password", as: AuthResponse.self) {
        $0.token != nil ? "token issued for \($0.username ?? "?")" : "no token"
    }
    decodeFixture("auth_mfa_challenge", as: AuthResponse.self) {
        ($0.mfaRequired == true && $0.token == nil)
            ? "challenge issued, no api token"
            : "UNEXPECTED: token present on an MFA account"
    }

    return failed
}
