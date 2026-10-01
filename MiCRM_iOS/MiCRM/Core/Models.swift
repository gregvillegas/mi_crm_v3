import Foundation

// Mirrors the DRF serializers in crm_project/serializers.py. Decoding uses
// `.convertFromSnakeCase`, so property names are the camelCase of the JSON keys.

// MARK: - Auth

struct AuthResponse: Decodable {
    let token: String?
    let userId: Int?
    let username: String?
    let email: String?
    let firstName: String?
    let lastName: String?
    let role: String?
    let roleDisplay: String?

    /// Present when the account has an authenticator enrolled: the caller must
    /// post `mfaToken` plus a code to `api-token-auth/mfa/`.
    let mfaRequired: Bool?
    let mfaToken: String?

    /// Present when the site requires MFA but this account has not enrolled.
    let mfaSetupRequired: Bool?
    let setupUrl: String?
    let detail: String?
}

struct CurrentUser: Decodable, Identifiable {
    let id: Int
    let username: String
    let email: String
    let firstName: String
    let lastName: String
    let role: String
    let initials: String?
    let mobileNumber: String?

    var displayName: String {
        let full = "\(firstName) \(lastName)".trimmingCharacters(in: .whitespaces)
        return full.isEmpty ? username : full
    }
}

// MARK: - Dashboard

struct DashboardSummary: Decodable {
    let user: DashboardUser
    let customers: CustomerStats
    let funnel: FunnelStats
    let proposals: ProposalStats
    let activities: ActivityStats
    let customerRequests: CustomerRequestStats
    let upcomingActivities: [SalesActivity]
    let recentProposals: [ProposalSummary]
}

struct DashboardUser: Decodable {
    let id: Int
    let name: String
    let role: String
    let roleDisplay: String
    let initials: String
}

struct CustomerStats: Decodable {
    let total: Int
    let active: Int
    let vip: Int
    let needsAttention: Int
}

struct FunnelStats: Decodable {
    let stages: [FunnelStageSummary]
    let totalValue: Double
    let totalCount: Int
}

struct FunnelStageSummary: Decodable, Identifiable {
    let stage: String
    let label: String
    let count: Int
    let value: Double

    var id: String { stage }
    var style: FunnelStageStyle { .from(stage) }
}

struct ProposalStats: Decodable {
    let total: Int
    let thisMonth: Int
    let awaitingApproval: Int
    let approved: Int
    let myPendingApprovals: Int
}

struct ActivityStats: Decodable {
    let total: Int
    let thisMonth: Int
    let completedThisMonth: Int
    let upcoming: Int
    let overdue: Int
}

struct CustomerRequestStats: Decodable {
    let minePending: Int
    let awaitingMyReview: Int
}

// MARK: - Customers

struct CustomerSummary: Decodable, Identifiable, Hashable {
    let id: Int
    let companyName: String
    let contactPersonName: String
    let contactPersonPosition: String?
    let email: String
    let phoneNumber: String?
    let industry: String?
    let territory: String?
    let displayStatus: String?
    let isActive: Bool
    let autoInactiveFlag: Bool
    let isMillionaireAccount: Bool
    let salespersonName: String?
    let salespersonInitials: String?

    static func == (lhs: CustomerSummary, rhs: CustomerSummary) -> Bool { lhs.id == rhs.id }
    func hash(into hasher: inout Hasher) { hasher.combine(id) }
}

struct CustomerContact: Decodable, Identifiable {
    let id: Int?
    let name: String
    let position: String?
    let email: String?
    let phone: String?
    let isPrimary: Bool
}

struct CustomerDetail: Decodable, Identifiable {
    let id: Int
    let companyName: String
    let contactPersonName: String
    let contactPersonPosition: String?
    let email: String
    let phoneNumber: String?
    let address: String?
    let industry: String?
    let territory: String?
    let displayStatus: String?
    let isActive: Bool
    let autoInactiveFlag: Bool
    let isMillionaireAccount: Bool
    let salespersonName: String?
    let contacts: [CustomerContact]
}

struct ChoiceOption: Decodable, Identifiable, Hashable {
    let value: String
    let label: String
    var id: String { value }
}

struct CustomerChoices: Decodable {
    let industries: [ChoiceOption]
    let territories: [ChoiceOption]
}

struct CustomerRequest: Decodable, Identifiable {
    let id: Int
    let companyName: String
    let contactPersonName: String
    let email: String
    let status: String
    let decisionNotes: String?
    let createdAt: String
    let reviewedAt: String?
    let requestedByName: String?
}

struct NewCustomerRequest: Encodable {
    let companyName: String
    let contactPersonName: String
    let contactPersonPosition: String?
    let email: String
    let phoneNumber: String?
    let address: String?
    let industry: String?
    let territory: String?
}

// MARK: - Funnel

struct FunnelEntry: Decodable, Identifiable {
    let id: Int
    let companyName: String
    let requirementDescription: String
    let cost: String
    let retail: String
    let stage: String
    let stageDisplay: String
    let probability: Int?
    let customerName: String?

    var style: FunnelStageStyle { .from(stage) }
    var retailValue: Double { Double(retail) ?? 0 }
}

// MARK: - Proposals

struct ProposalSummary: Decodable, Identifiable {
    let id: Int
    let proposalNumber: String
    let subject: String
    let customerName: String?
    let totalAmount: String?
    let currency: String
    let status: String?
    let statusDisplay: String?
    let approvalStatus: String?

    var amount: Double { Double(totalAmount ?? "0") ?? 0 }
}

struct ProposalApprovalStep: Decodable, Identifiable {
    let id: Int
    let level: Int
    let approverName: String?
    let status: String
    let comment: String?
    let isCurrent: Bool
}

struct ProposalItem: Decodable, Identifiable {
    let id: Int?
    let partNumber: String?
    let description: String
    let quantity: String?
    let unitPrice: String?

    var identifier: String { "\(id ?? 0)-\(description)" }
}

extension ProposalItem {
    var idValue: Int { id ?? description.hashValue }
}

struct ProposalDetail: Decodable, Identifiable {
    let id: Int
    let proposalNumber: String
    let referenceNumber: String?
    let subject: String
    let statusDisplay: String?
    let approvalStatus: String
    let approvalRequired: Bool
    let canCurrentUserApprove: Bool
    let totalAmount: String?
    let subtotal: String?
    let taxAmount: String?
    let currency: String
    let customer: CustomerSummary?
    let createdByName: String?
    let approvalSteps: [ProposalApprovalStep]

    var amount: Double { Double(totalAmount ?? "0") ?? 0 }
}

struct PendingApproval: Decodable, Identifiable {
    let id: Int
    let proposalId: Int
    let proposalNumber: String
    let customerName: String?
    let subject: String
    let totalAmount: String?
    let currency: String
    let level: Int

    var amount: Double { Double(totalAmount ?? "0") ?? 0 }
}

struct ApprovalDecision: Encodable {
    let comment: String
}

// MARK: - Activities

struct ActivityType: Decodable, Identifiable, Hashable {
    let id: Int
    let name: String
    let icon: String
    let color: String
}

struct SalesActivity: Decodable, Identifiable {
    let id: Int
    let title: String
    let description: String?
    let activityTypeDetails: ActivityType?
    let customerName: String?
    let status: String
    let statusDisplay: String?
    let priority: String
    let scheduledStart: Date?
    let scheduledEnd: Date?
    let actualEnd: Date?

    var isOverdue: Bool {
        guard let end = scheduledEnd, status == "planned" || status == "in_progress" else { return false }
        return end < Date()
    }
}

struct NewActivity: Encodable {
    let title: String
    let description: String?
    let activityType: Int
    let customer: Int?
    let status: String
    let priority: String
    let scheduledStart: String?
    let scheduledEnd: String?
    let notes: String?
}

struct ActivityCompletion: Encodable {
    let notes: String?
}

// MARK: - Campaigns

struct CampaignSummary: Decodable, Identifiable {
    let id: Int
    let name: String
    let subject: String
    let status: String
    let totalRecipients: Int?
    let sentCount: Int?
    let failedCount: Int?
    let scheduledFor: Date?
}

// MARK: - Generic

struct APIMessage: Decodable {
    let detail: String?
}
