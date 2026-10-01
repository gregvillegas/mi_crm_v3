import SwiftUI

@MainActor
@Observable
final class ProposalListModel {
    enum Filter: String, CaseIterable, Identifiable {
        case all, pending, approved
        var id: String { rawValue }

        var label: String {
            switch self {
            case .all: return "All"
            case .pending: return "Awaiting"
            case .approved: return "Approved"
            }
        }

        var apiValue: String? {
            switch self {
            case .all: return nil
            case .pending: return "pending"
            case .approved: return "approved"
            }
        }
    }

    var proposals: [ProposalSummary] = []
    var isLoading = false
    var errorMessage: String?
    var search = ""
    var filter: Filter = .all

    private var searchTask: Task<Void, Never>?

    func load() async {
        if proposals.isEmpty { isLoading = true }
        errorMessage = nil
        do {
            proposals = try await APIClient.shared.proposals(
                search: search.isEmpty ? nil : search,
                approvalStatus: filter.apiValue
            )
        } catch {
            errorMessage = (error as? APIError)?.errorDescription ?? error.localizedDescription
        }
        isLoading = false
    }

    func searchChanged() {
        searchTask?.cancel()
        searchTask = Task {
            try? await Task.sleep(for: .milliseconds(300))
            guard !Task.isCancelled else { return }
            await load()
        }
    }
}

struct ProposalListView: View {
    @State private var model = ProposalListModel()

    var body: some View {
        Group {
            if model.isLoading {
                LoadingState()
            } else if let message = model.errorMessage, model.proposals.isEmpty {
                ErrorState(message: message) { Task { await model.load() } }
            } else {
                list
            }
        }
        .background(Palette.canvas)
        .navigationTitle("Proposals")
        .searchable(text: Binding(
            get: { model.search },
            set: { model.search = $0; model.searchChanged() }
        ), prompt: "Number, subject, or customer")
        .toolbar {
            ToolbarItem {
                NavigationLink {
                    ApprovalInboxView()
                } label: {
                    Image(systemName: "checkmark.seal")
                }
                .accessibilityLabel("Approvals waiting on you")
            }
        }
        .task { await model.load() }
        .refreshable { await model.load() }
    }

    private var list: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                Picker("Filter", selection: Binding(
                    get: { model.filter },
                    set: { model.filter = $0; Task { await model.load() } }
                )) {
                    ForEach(ProposalListModel.Filter.allCases) { filter in
                        Text(filter.label).tag(filter)
                    }
                }
                .pickerStyle(.segmented)

                if model.proposals.isEmpty {
                    EmptyState(
                        title: "Nothing here",
                        message: model.search.isEmpty
                            ? "Proposals you raise, and your team's, will show up here."
                            : "Nothing matched “\(model.search)”.",
                        systemImage: "doc.text"
                    )
                    .frame(minHeight: 260)
                } else {
                    RowCard {
                        ForEach(Array(model.proposals.enumerated()), id: \.element.id) { index, proposal in
                            if index > 0 { Hairline() }
                            NavigationLink {
                                ProposalDetailView(proposalId: proposal.id)
                            } label: {
                                ProposalRow(proposal: proposal)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }
            }
            .padding(.horizontal, Metrics.gutter)
            .padding(.vertical, 16)
        }
        .background(Palette.canvas)
    }
}

struct ProposalRow: View {
    let proposal: ProposalSummary

    var body: some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text(proposal.subject)
                    .font(TypeScale.rowTitle)
                    .foregroundStyle(Palette.ink)
                    .lineLimit(1)

                HStack(spacing: 6) {
                    Text(proposal.proposalNumber)
                        .font(TypeScale.caption.monospacedDigit())
                        .foregroundStyle(Palette.inkFaint)
                    if let customer = proposal.customerName {
                        Text(customer)
                            .font(TypeScale.caption)
                            .foregroundStyle(Palette.inkMuted)
                            .lineLimit(1)
                    }
                }
            }

            Spacer(minLength: 8)

            VStack(alignment: .trailing, spacing: 5) {
                Text(Format.compactCurrency(proposal.amount, code: proposal.currency))
                    .font(TypeScale.figureSmall())
                    .foregroundStyle(Palette.ink)
                StatusTag(
                    text: StatusPalette.label(for: proposal.approvalStatus),
                    color: StatusPalette.color(for: proposal.approvalStatus)
                )
            }
        }
        .padding(.vertical, 12)
        .contentShape(Rectangle())
    }
}
