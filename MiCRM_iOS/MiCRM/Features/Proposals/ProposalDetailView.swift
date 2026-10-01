import SwiftUI

@MainActor
@Observable
final class ProposalDetailModel {
    var proposal: ProposalDetail?
    var isLoading = true
    var errorMessage: String?
    var isDeciding = false
    var pdfURL: URL?
    var isDownloading = false

    func load(id: Int) async {
        errorMessage = nil
        do {
            proposal = try await APIClient.shared.proposal(id: id)
        } catch {
            errorMessage = (error as? APIError)?.errorDescription ?? error.localizedDescription
        }
        isLoading = false
    }

    /// Returns an error message, or nil on success.
    func decide(id: Int, approve: Bool, comment: String) async -> String? {
        isDeciding = true
        defer { isDeciding = false }
        do {
            try await APIClient.shared.decideProposal(id: id, approve: approve, comment: comment)
            await load(id: id)
            return nil
        } catch {
            return (error as? APIError)?.errorDescription ?? error.localizedDescription
        }
    }

    func downloadPDF(id: Int, number: String) async {
        isDownloading = true
        defer { isDownloading = false }
        pdfURL = try? await APIClient.shared.downloadProposalPDF(id: id, number: number)
    }
}

struct ProposalDetailView: View {
    let proposalId: Int

    @State private var model = ProposalDetailModel()
    @State private var decisionSheet: Decision?
    @State private var comment = ""
    @State private var decisionError: String?

    enum Decision: Identifiable {
        case approve, reject
        var id: String { self == .approve ? "approve" : "reject" }
        var isApproval: Bool { self == .approve }
        var verb: String { self == .approve ? "Approve" : "Reject" }
    }

    var body: some View {
        Group {
            if model.isLoading {
                LoadingState()
            } else if let message = model.errorMessage, model.proposal == nil {
                ErrorState(message: message) { Task { await model.load(id: proposalId) } }
            } else if let proposal = model.proposal {
                content(proposal)
            }
        }
        .background(Palette.canvas)
        .navigationTitle(model.proposal?.proposalNumber ?? "Proposal")
        .inlineNavigationTitle()
        .toolbar {
            ToolbarItem {
                Button {
                    guard let proposal = model.proposal else { return }
                    Task { await model.downloadPDF(id: proposal.id, number: proposal.proposalNumber) }
                } label: {
                    if model.isDownloading {
                        ProgressView()
                    } else {
                        Image(systemName: "arrow.down.doc")
                    }
                }
                .disabled(model.proposal == nil || model.isDownloading)
                .accessibilityLabel("Download quotation PDF")
            }
        }
        .sheet(item: $decisionSheet) { decision in
            decisionForm(decision)
        }
        .quickLook(url: $model.pdfURL)
        .task { await model.load(id: proposalId) }
    }

    private func content(_ proposal: ProposalDetail) -> some View {
        ScreenScroll {
            VStack(alignment: .leading, spacing: 14) {
                Text(proposal.subject)
                    .font(.system(size: 23, weight: .bold))
                    .tracking(-0.4)
                    .foregroundStyle(Palette.ink)
                    .fixedSize(horizontal: false, vertical: true)

                Text(Format.currency(proposal.amount, code: proposal.currency))
                    .font(TypeScale.figure(32))
                    .tracking(-0.8)
                    .foregroundStyle(Palette.ink)

                HStack(spacing: 8) {
                    StatusTag(
                        text: StatusPalette.label(for: proposal.approvalStatus),
                        color: StatusPalette.color(for: proposal.approvalStatus)
                    )
                    if let status = proposal.statusDisplay {
                        StatusTag(text: status, color: Palette.inkMuted)
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(Metrics.gutter)
            .background(Palette.surface, in: RoundedRectangle(cornerRadius: Metrics.cardRadius))

            if proposal.canCurrentUserApprove {
                decisionButtons
            }

            if !proposal.approvalSteps.isEmpty {
                approvalChain(proposal)
            }

            figures(proposal)

            if let customer = proposal.customer {
                VStack(alignment: .leading, spacing: 10) {
                    SectionHeading(title: "Customer")
                    RowCard {
                        NavigationLink {
                            CustomerDetailView(customerId: customer.id)
                        } label: {
                            PlainRow(
                                title: customer.companyName,
                                subtitle: customer.contactPersonName
                            ) {
                                Image(systemName: "chevron.right")
                                    .font(.system(size: 12, weight: .semibold))
                                    .foregroundStyle(Palette.inkFaint)
                            }
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
        }
    }

    private var decisionButtons: some View {
        HStack(spacing: 10) {
            Button("Approve") { comment = ""; decisionError = nil; decisionSheet = .approve }
                .buttonStyle(PrimaryButtonStyle())
            Button("Reject") { comment = ""; decisionError = nil; decisionSheet = .reject }
                .buttonStyle(SecondaryButtonStyle())
        }
    }

    // The chain is a sequence, so numbering it is meaningful here.
    private func approvalChain(_ proposal: ProposalDetail) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionHeading(title: "Approval chain")
            RowCard {
                ForEach(Array(proposal.approvalSteps.enumerated()), id: \.element.id) { index, step in
                    if index > 0 { Hairline() }
                    HStack(spacing: 12) {
                        Text("\(step.level)")
                            .font(TypeScale.caption.monospacedDigit())
                            .foregroundStyle(StatusPalette.color(for: step.status))
                            .frame(width: 24, height: 24)
                            .background(
                                Circle().fill(StatusPalette.color(for: step.status).opacity(0.12))
                            )

                        VStack(alignment: .leading, spacing: 3) {
                            Text(step.approverName ?? "Unassigned")
                                .font(TypeScale.rowTitle)
                                .foregroundStyle(Palette.ink)
                            if let comment = step.comment, !comment.isEmpty {
                                Text(comment)
                                    .font(TypeScale.caption)
                                    .foregroundStyle(Palette.inkMuted)
                            }
                        }

                        Spacer(minLength: 8)

                        StatusTag(
                            text: step.isCurrent && step.status == "pending"
                                ? "With them now"
                                : StatusPalette.label(for: step.status),
                            color: StatusPalette.color(for: step.status)
                        )
                    }
                    .padding(.vertical, 12)
                }
            }
        }
    }

    private func figures(_ proposal: ProposalDetail) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionHeading(title: "Figures")
            RowCard {
                MetricRow(
                    label: "Subtotal",
                    value: Format.currency(Double(proposal.subtotal ?? "0") ?? 0, code: proposal.currency)
                )
                Hairline()
                MetricRow(
                    label: "Tax",
                    value: Format.currency(Double(proposal.taxAmount ?? "0") ?? 0, code: proposal.currency)
                )
                Hairline()
                MetricRow(
                    label: "Total",
                    value: Format.currency(proposal.amount, code: proposal.currency)
                )
                if let reference = proposal.referenceNumber, !reference.isEmpty {
                    Hairline()
                    MetricRow(label: "Reference", value: reference)
                }
                if let author = proposal.createdByName {
                    Hairline()
                    MetricRow(label: "Raised by", value: author)
                }
            }
        }
    }

    private func decisionForm(_ decision: Decision) -> some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    Text(
                        decision.isApproval
                            ? "This moves the proposal to the next approver, or marks it fully approved if you're the last."
                            : "Rejecting ends the approval chain. The salesperson is notified with your reason."
                    )
                    .font(TypeScale.body)
                    .foregroundStyle(Palette.inkMuted)
                    .fixedSize(horizontal: false, vertical: true)

                    VStack(alignment: .leading, spacing: 6) {
                        Text(decision.isApproval ? "Comment (optional)" : "Reason")
                            .font(TypeScale.caption)
                            .foregroundStyle(Palette.inkMuted)
                        TextEditor(text: $comment)
                            .font(TypeScale.body)
                            .frame(height: 120)
                            .padding(8)
                            .background(Palette.surface, in: RoundedRectangle(cornerRadius: Metrics.controlRadius))
                            .overlay(
                                RoundedRectangle(cornerRadius: Metrics.controlRadius)
                                    .stroke(Palette.hairline, lineWidth: 1)
                            )
                    }

                    if let decisionError {
                        Text(decisionError)
                            .font(TypeScale.caption)
                            .foregroundStyle(Palette.critical)
                    }

                    Button {
                        Task {
                            let error = await model.decide(
                                id: proposalId,
                                approve: decision.isApproval,
                                comment: comment
                            )
                            if let error {
                                decisionError = error
                            } else {
                                decisionSheet = nil
                            }
                        }
                    } label: {
                        if model.isDeciding {
                            ProgressView().tint(.white)
                        } else {
                            Text(decision.verb)
                        }
                    }
                    .buttonStyle(PrimaryButtonStyle())
                    .disabled(model.isDeciding || (!decision.isApproval && comment.trimmingCharacters(in: .whitespaces).isEmpty))

                    Spacer()
                }
                .padding(Metrics.gutter)
            }
            .background(Palette.canvas)
            .navigationTitle("\(decision.verb) proposal")
            .inlineNavigationTitle()
            .toolbar {
                ToolbarItem {
                    Button("Cancel") { decisionSheet = nil }
                }
            }
        }
    }
}
