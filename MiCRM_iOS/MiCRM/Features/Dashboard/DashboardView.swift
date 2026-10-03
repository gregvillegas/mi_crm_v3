import SwiftUI

@MainActor
@Observable
final class DashboardModel {
    var summary: DashboardSummary?
    var errorMessage: String?
    var isLoading = false

    func load() async {
        if summary == nil { isLoading = true }
        errorMessage = nil
        do {
            summary = try await APIClient.shared.dashboard()
        } catch {
            errorMessage = (error as? APIError)?.errorDescription ?? error.localizedDescription
        }
        isLoading = false
    }
}

struct DashboardView: View {
    @Environment(Session.self) private var session
    @State private var model = DashboardModel()

    var body: some View {
        Group {
            if model.isLoading {
                LoadingState()
            } else if let message = model.errorMessage, model.summary == nil {
                ErrorState(message: message) { Task { await model.load() } }
            } else if let summary = model.summary {
                content(summary)
            } else {
                LoadingState()
            }
        }
        .background(Palette.canvas)
        .navigationTitle(greeting)
        .task { await model.load() }
        .refreshable { await model.load() }
    }

    private var greeting: String {
        guard let name = session.user?.firstName, !name.isEmpty else { return "Home" }
        return name
    }

    private func content(_ summary: DashboardSummary) -> some View {
        ScreenScroll {
            if let quote = summary.quote, !quote.isEmpty {
                QuoteCard(quote: quote)
            }

            PipelineRail(stages: summary.funnel.stages, totalValue: summary.funnel.totalValue)

            needsYou(summary)

            schedule(summary)

            recentProposals(summary)

            reach(summary)
        }
    }

    // Only rendered when there is genuinely something waiting, so the section
    // is a signal rather than permanent furniture.
    @ViewBuilder
    private func needsYou(_ summary: DashboardSummary) -> some View {
        let approvals = summary.proposals.myPendingApprovals
        let requests = summary.customerRequests.awaitingMyReview
        let overdue = summary.activities.overdue

        if approvals > 0 || requests > 0 || overdue > 0 {
            VStack(alignment: .leading, spacing: 10) {
                SectionHeading(title: "Needs you")

                if approvals > 0 {
                    NavigationLink {
                        ApprovalInboxView()
                    } label: {
                        ActionPrompt(
                            count: approvals,
                            title: approvals == 1 ? "Proposal to approve" : "Proposals to approve",
                            subtitle: "Waiting on your decision",
                            systemImage: "checkmark.seal"
                        )
                    }
                    .buttonStyle(.plain)
                }

                if requests > 0 {
                    NavigationLink {
                        PendingCustomerRequestsView()
                    } label: {
                        ActionPrompt(
                            count: requests,
                            title: requests == 1 ? "New customer request" : "New customer requests",
                            subtitle: "Submitted by your team",
                            systemImage: "person.badge.plus"
                        )
                    }
                    .buttonStyle(.plain)
                }

                if overdue > 0 {
                    NavigationLink {
                        ActivityListView(initialFilter: .overdue)
                    } label: {
                        ActionPrompt(
                            count: overdue,
                            title: overdue == 1 ? "Overdue activity" : "Overdue activities",
                            subtitle: "Past their scheduled end",
                            systemImage: "clock.badge.exclamationmark"
                        )
                    }
                    .buttonStyle(.plain)
                }
            }
        }
    }

    @ViewBuilder
    private func schedule(_ summary: DashboardSummary) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionHeading(title: "Coming up")

            if summary.upcomingActivities.isEmpty {
                RowCard {
                    Text("Nothing scheduled. Log an activity after your next visit.")
                        .font(TypeScale.body)
                        .foregroundStyle(Palette.inkMuted)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.vertical, 16)
                }
            } else {
                RowCard {
                    ForEach(Array(summary.upcomingActivities.enumerated()), id: \.element.id) { index, activity in
                        if index > 0 { Hairline() }
                        PlainRow(
                            title: activity.title,
                            subtitle: [activity.customerName, Format.schedule(activity.scheduledStart)]
                                .compactMap { $0 }
                                .joined(separator: " · ")
                        ) {
                            if activity.isOverdue {
                                StatusTag(text: "Overdue", color: Palette.critical)
                            }
                        }
                    }
                }
            }
        }
    }

    @ViewBuilder
    private func recentProposals(_ summary: DashboardSummary) -> some View {
        if !summary.recentProposals.isEmpty {
            VStack(alignment: .leading, spacing: 10) {
                SectionHeading(title: "Recent proposals")

                RowCard {
                    ForEach(Array(summary.recentProposals.enumerated()), id: \.element.id) { index, proposal in
                        if index > 0 { Hairline() }
                        NavigationLink {
                            ProposalDetailView(proposalId: proposal.id)
                        } label: {
                            PlainRow(
                                title: proposal.subject,
                                subtitle: [proposal.proposalNumber, proposal.customerName]
                                    .compactMap { $0 }
                                    .joined(separator: " · ")
                            ) {
                                Text(Format.compactCurrency(proposal.amount, code: proposal.currency))
                                    .font(TypeScale.figureSmall())
                                    .foregroundStyle(Palette.ink)
                            }
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
        }
    }

    private func reach(_ summary: DashboardSummary) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionHeading(title: "Your book")

            RowCard {
                MetricRow(label: "Customers", value: "\(summary.customers.total)")
                Hairline()
                MetricRow(label: "Key accounts", value: "\(summary.customers.vip)")
                Hairline()
                MetricRow(label: "Proposals this month", value: "\(summary.proposals.thisMonth)")
                Hairline()
                MetricRow(
                    label: "Activities completed this month",
                    value: "\(summary.activities.completedThisMonth)"
                )
            }
        }
    }
}

struct MetricRow: View {
    let label: String
    let value: String

    var body: some View {
        HStack {
            Text(label)
                .font(TypeScale.body)
                .foregroundStyle(Palette.ink)
            Spacer(minLength: 8)
            Text(value)
                .font(TypeScale.figureSmall())
                .foregroundStyle(Palette.ink)
        }
        .padding(.vertical, 13)
    }
}

/// Inspiration shown at the top of the dashboard — the same motivational quote
/// the web app surfaces on login (core/quotes.py).
struct QuoteCard: View {
    let quote: String

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: "quote.opening")
                .font(.system(size: 15, weight: .semibold))
                .foregroundStyle(Palette.brand)
            Text(quote)
                .font(TypeScale.body)
                .foregroundStyle(Palette.ink)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .background(Palette.surface, in: RoundedRectangle(cornerRadius: Metrics.cardRadius))
    }
}
