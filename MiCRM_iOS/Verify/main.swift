import Foundation

// Executable harness that exercises the app's pure logic against the real
// source files. Compiled and run by Verify/run.sh; not part of the app target.

var failures = 0
func check(_ label: String, _ actual: String, _ expected: String) {
    if actual == expected {
        print("  ok    \(label)  ->  \(actual)")
    } else {
        failures += 1
        print("  FAIL  \(label)\n          expected: \(expected)\n          actual:   \(actual)")
    }
}
func check(_ label: String, _ condition: Bool) {
    if condition { print("  ok    \(label)") }
    else { failures += 1; print("  FAIL  \(label)") }
}

print("\nServer address normalisation")
check("bare domain gets https",
      APIClient.normalizedBaseURL(host: "micrm.microimageph.com")?.absoluteString ?? "nil",
      "https://micrm.microimageph.com/api/v1/")
check("private ip:port gets http",
      APIClient.normalizedBaseURL(host: "10.20.20.2:8001")?.absoluteString ?? "nil",
      "http://10.20.20.2:8001/api/v1/")
check("localhost gets http",
      APIClient.normalizedBaseURL(host: "localhost:8000")?.absoluteString ?? "nil",
      "http://localhost:8000/api/v1/")
check("172.16-31 is private",
      APIClient.normalizedBaseURL(host: "172.20.0.5:8001")?.absoluteString ?? "nil",
      "http://172.20.0.5:8001/api/v1/")
check("172.32 is not private",
      APIClient.normalizedBaseURL(host: "172.32.0.5")?.absoluteString ?? "nil",
      "https://172.32.0.5/api/v1/")
check("public domain keeps https even with a port",
      APIClient.normalizedBaseURL(host: "crm.example.com:8443")?.absoluteString ?? "nil",
      "https://crm.example.com:8443/api/v1/")
check("explicit scheme preserved",
      APIClient.normalizedBaseURL(host: "https://crm.example.com")?.absoluteString ?? "nil",
      "https://crm.example.com/api/v1/")
check("trailing slashes trimmed",
      APIClient.normalizedBaseURL(host: "https://crm.example.com///")?.absoluteString ?? "nil",
      "https://crm.example.com/api/v1/")
check("api/v1 not doubled",
      APIClient.normalizedBaseURL(host: "https://crm.example.com/api/v1")?.absoluteString ?? "nil",
      "https://crm.example.com/api/v1/")
check("whitespace tolerated",
      APIClient.normalizedBaseURL(host: "  crm.example.com  ")?.absoluteString ?? "nil",
      "https://crm.example.com/api/v1/")
check("empty host is nil", APIClient.normalizedBaseURL(host: "") == nil)

print("\nCurrency formatting")
check("compact millions", Format.compactCurrency(1_250_000), "₱1.3M")
check("compact thousands", Format.compactCurrency(850_000), "₱850K")
check("small amounts stay exact", Format.compactCurrency(4_500), "₱4,500")
check("zero", Format.compactCurrency(0), "₱0")

print("\nDate parsing (the three shapes DRF emits)")
check("ISO with fractional seconds", DateParsing.parse("2026-09-19T14:30:00.123456Z") != nil)
check("ISO without fraction", DateParsing.parse("2026-09-19T14:30:00Z") != nil)
check("date only", DateParsing.parse("2026-09-19") != nil)
check("garbage rejected", DateParsing.parse("not a date") == nil)

print("\nStatus vocabulary")
check("approved label", StatusPalette.label(for: "approved"), "Approved")
check("underscores become spaces", StatusPalette.label(for: "in_progress"), "In Progress")
check("missing status", StatusPalette.label(for: nil), "Unknown")

print("\nInitials")
check("two words", Format.initials(from: "Global Logistics"), "GL")
check("single word", Format.initials(from: "Acme"), "A")
check("empty", Format.initials(from: ""), "?")

print("\nFunnel stage mapping")
check("known stage", FunnelStageStyle.from("services") == .services)
check("unknown stage falls back", FunnelStageStyle.from("nonsense") == .quoted)
check("all four stages defined", FunnelStageStyle.allCases.count == 4)

print("\nDecoding a dashboard payload from the live API shape")
let payload = """
{
  "user": {"id": 1, "name": "Ana Cruz", "role": "salesperson",
           "role_display": "Salesperson", "initials": "AC"},
  "customers": {"total": 42, "active": 40, "vip": 3, "needs_attention": 2},
  "funnel": {"stages": [
      {"stage": "quoted", "label": "Newly Quoted", "count": 4, "value": 1250000.0},
      {"stage": "closable", "label": "Closable Deals", "count": 2, "value": 500000.0},
      {"stage": "project", "label": "Green Funnel", "count": 0, "value": 0.0},
      {"stage": "services", "label": "Blue Funnel", "count": 1, "value": 90000.0}],
    "total_value": 1840000.0, "total_count": 7},
  "proposals": {"total": 12, "this_month": 3, "awaiting_approval": 2,
                "approved": 8, "my_pending_approvals": 1},
  "activities": {"total": 30, "this_month": 6, "completed_this_month": 4,
                 "upcoming": 2, "overdue": 1},
  "customer_requests": {"mine_pending": 1, "awaiting_my_review": 0},
  "upcoming_activities": [
    {"id": 9, "title": "Site visit", "description": null, "activity_type": 1,
     "activity_type_details": {"id": 1, "name": "Meeting", "icon": "fas fa-users", "color": "primary"},
     "customer_name": "Global Logistics", "status": "planned", "status_display": "Planned",
     "priority": "high", "scheduled_start": "2026-09-20T09:00:00Z",
     "scheduled_end": "2026-09-20T10:00:00Z", "actual_start": null, "actual_end": null,
     "created_at": "2026-09-19T08:00:00Z"}],
  "recent_proposals": [
    {"id": 5, "proposal_number": "PROP-8821", "subject": "Core switch refresh",
     "customer_name": "Global Logistics", "total_amount": "450000.00", "currency": "PHP",
     "status": "sent", "status_display": "Sent", "approval_status": "approved"}]
}
""".data(using: .utf8)!

let decoder = JSONDecoder()
decoder.keyDecodingStrategy = .convertFromSnakeCase
decoder.dateDecodingStrategy = .custom { d in
    let raw = try d.singleValueContainer().decode(String.self)
    guard let date = DateParsing.parse(raw) else {
        throw DecodingError.dataCorrupted(.init(codingPath: d.codingPath, debugDescription: raw))
    }
    return date
}

do {
    let summary = try decoder.decode(DashboardSummary.self, from: payload)
    check("user decoded", summary.user.name, "Ana Cruz")
    check("customer count", "\(summary.customers.total)", "42")
    check("four funnel stages", summary.funnel.stages.count == 4)
    check("pipeline total", Format.currency(summary.funnel.totalValue), "₱1,840,000")
    check("stage maps to its colour identity", summary.funnel.stages[3].style == .services)
    check("nested activity decoded", summary.upcomingActivities.first?.title ?? "", "Site visit")
    check("activity date decoded", summary.upcomingActivities.first?.scheduledStart != nil)
    check("proposal amount parsed", summary.recentProposals.first?.amount == 450_000)
    check("my pending approvals", "\(summary.proposals.myPendingApprovals)", "1")
} catch {
    failures += 1
    print("  FAIL  dashboard decode threw: \(error)")
}

print("\nDecoding the MFA challenge shape (no token present)")
let challenge = #"{"mfa_required": true, "mfa_token": "abc.def", "expires_in": 300, "detail": "Enter the code."}"#
    .data(using: .utf8)!
do {
    let response = try decoder.decode(AuthResponse.self, from: challenge)
    check("challenge flagged", response.mfaRequired == true)
    check("interim token present", response.mfaToken ?? "", "abc.def")
    check("no api token handed out", response.token == nil)
} catch {
    failures += 1
    print("  FAIL  auth challenge decode threw: \(error)")
}

failures += runContractChecks(decoder: decoder)

print("\n\(failures == 0 ? "All checks passed." : "\(failures) check(s) failed.")\n")
exit(failures == 0 ? 0 : 1)
