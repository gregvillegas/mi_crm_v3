import SwiftUI

@MainActor
@Observable
final class ApprovalInboxModel {
    var approvals: [PendingApproval] = []
    var isLoading = true
    var errorMessage: String?

    func load() async {
        errorMessage = nil
        do {
            approvals = try await APIClient.shared.pendingApprovals()
        } catch {
            errorMessage = (error as? APIError)?.errorDescription ?? error.localizedDescription
        }
        isLoading = false
    }
}

/// Only shows steps that are actually the caller's turn — the server already
/// filters to the current pending level, so nothing here is blocked behind
/// someone else.
struct ApprovalInboxView: View {
    @State private var model = ApprovalInboxModel()

    var body: some View {
        Group {
            if model.isLoading {
                LoadingState()
            } else if let message = model.errorMessage, model.approvals.isEmpty {
                ErrorState(message: message) { Task { await model.load() } }
            } else if model.approvals.isEmpty {
                EmptyState(
                    title: "Nothing waiting",
                    message: "When a proposal reaches your level in the approval chain, it lands here.",
                    systemImage: "checkmark.seal"
                )
            } else {
                ScreenScroll {
                    Text(
                        model.approvals.count == 1
                            ? "1 proposal is waiting on you."
                            : "\(model.approvals.count) proposals are waiting on you."
                    )
                    .font(TypeScale.body)
                    .foregroundStyle(Palette.inkMuted)

                    RowCard {
                        ForEach(Array(model.approvals.enumerated()), id: \.element.id) { index, approval in
                            if index > 0 { Hairline() }
                            NavigationLink {
                                ProposalDetailView(proposalId: approval.proposalId)
                            } label: {
                                HStack(spacing: 12) {
                                    VStack(alignment: .leading, spacing: 4) {
                                        Text(approval.subject)
                                            .font(TypeScale.rowTitle)
                                            .foregroundStyle(Palette.ink)
                                            .lineLimit(1)
                                        Text(
                                            [approval.proposalNumber, approval.customerName]
                                                .compactMap { $0 }
                                                .joined(separator: " · ")
                                        )
                                        .font(TypeScale.caption)
                                        .foregroundStyle(Palette.inkMuted)
                                        .lineLimit(1)
                                    }

                                    Spacer(minLength: 8)

                                    VStack(alignment: .trailing, spacing: 5) {
                                        Text(Format.compactCurrency(approval.amount, code: approval.currency))
                                            .font(TypeScale.figureSmall())
                                            .foregroundStyle(Palette.ink)
                                        StatusTag(text: "Level \(approval.level)", color: Palette.warning)
                                    }
                                }
                                .padding(.vertical, 12)
                                .contentShape(Rectangle())
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }
            }
        }
        .background(Palette.canvas)
        .navigationTitle("Approvals")
        .inlineNavigationTitle()
        .task { await model.load() }
        .refreshable { await model.load() }
    }
}
