import SwiftUI

@MainActor
@Observable
final class CampaignListModel {
    var campaigns: [CampaignSummary] = []
    var isLoading = true
    var errorMessage: String?

    func load() async {
        errorMessage = nil
        do {
            campaigns = try await APIClient.shared.campaigns()
        } catch {
            errorMessage = (error as? APIError)?.errorDescription ?? error.localizedDescription
        }
        isLoading = false
    }
}

/// Read-only on mobile. Building and sending a campaign is a desk task, so the
/// app shows delivery progress rather than trying to be an editor.
struct CampaignListView: View {
    @State private var model = CampaignListModel()

    var body: some View {
        Group {
            if model.isLoading {
                LoadingState()
            } else if let message = model.errorMessage, model.campaigns.isEmpty {
                ErrorState(message: message) { Task { await model.load() } }
            } else if model.campaigns.isEmpty {
                EmptyState(
                    title: "No campaigns",
                    message: "Email campaigns you can see will be listed here with their delivery progress.",
                    systemImage: "envelope"
                )
            } else {
                ScreenScroll {
                    RowCard {
                        ForEach(Array(model.campaigns.enumerated()), id: \.element.id) { index, campaign in
                            if index > 0 { Hairline() }
                            CampaignRow(campaign: campaign)
                        }
                    }
                }
            }
        }
        .background(Palette.canvas)
        .navigationTitle("Campaigns")
        .inlineNavigationTitle()
        .task { await model.load() }
        .refreshable { await model.load() }
    }
}

private struct CampaignRow: View {
    let campaign: CampaignSummary

    private var progress: Double {
        guard let total = campaign.totalRecipients, total > 0 else { return 0 }
        return Double(campaign.sentCount ?? 0) / Double(total)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                VStack(alignment: .leading, spacing: 3) {
                    Text(campaign.name)
                        .font(TypeScale.rowTitle)
                        .foregroundStyle(Palette.ink)
                        .lineLimit(1)
                    Text(campaign.subject)
                        .font(TypeScale.caption)
                        .foregroundStyle(Palette.inkMuted)
                        .lineLimit(1)
                }
                Spacer(minLength: 8)
                StatusTag(
                    text: StatusPalette.label(for: campaign.status),
                    color: StatusPalette.color(for: campaign.status)
                )
            }

            if let total = campaign.totalRecipients, total > 0 {
                ProgressView(value: progress)
                    .tint(Palette.positive)

                HStack(spacing: 10) {
                    Text("\(campaign.sentCount ?? 0) of \(total) sent")
                    if let failed = campaign.failedCount, failed > 0 {
                        Text("\(failed) failed")
                            .foregroundStyle(Palette.critical)
                    }
                }
                .font(TypeScale.caption.monospacedDigit())
                .foregroundStyle(Palette.inkFaint)
            }
        }
        .padding(.vertical, 13)
    }
}
