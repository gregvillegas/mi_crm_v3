import SwiftUI

@MainActor
@Observable
final class FunnelModel {
    var entries: [FunnelEntry] = []
    var isLoading = true
    var errorMessage: String?
    var stage: String?

    func load() async {
        errorMessage = nil
        do {
            entries = try await APIClient.shared.funnel(stage: stage)
        } catch {
            errorMessage = (error as? APIError)?.errorDescription ?? error.localizedDescription
        }
        isLoading = false
    }

    var total: Double { entries.reduce(0) { $0 + $1.retailValue } }
}

struct FunnelView: View {
    @State private var model = FunnelModel()

    var body: some View {
        Group {
            if model.isLoading {
                LoadingState()
            } else if let message = model.errorMessage, model.entries.isEmpty {
                ErrorState(message: message) { Task { await model.load() } }
            } else {
                content
            }
        }
        .background(Palette.canvas)
        .navigationTitle("Funnel")
        .inlineNavigationTitle()
        .task { await model.load() }
        .refreshable { await model.load() }
    }

    private var content: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                stageFilter

                if model.entries.isEmpty {
                    EmptyState(
                        title: "No deals in this stage",
                        message: "Funnel entries are created from the CRM website when a quote goes out.",
                        systemImage: "chart.bar"
                    )
                    .frame(minHeight: 260)
                } else {
                    HStack {
                        Text("\(model.entries.count) \(model.entries.count == 1 ? "deal" : "deals")")
                            .font(TypeScale.body)
                            .foregroundStyle(Palette.inkMuted)
                        Spacer()
                        Text(Format.currency(model.total))
                            .font(TypeScale.figureSmall(18))
                            .foregroundStyle(Palette.ink)
                    }

                    RowCard {
                        ForEach(Array(model.entries.enumerated()), id: \.element.id) { index, entry in
                            if index > 0 { Hairline() }
                            NavigationLink {
                                FunnelDetailView(entry: entry)
                            } label: {
                                PlainRow(
                                    title: entry.companyName,
                                    subtitle: entry.requirementDescription,
                                    accent: entry.style.color
                                ) {
                                    VStack(alignment: .trailing, spacing: 4) {
                                        Text(Format.compactCurrency(entry.retailValue))
                                            .font(TypeScale.figureSmall())
                                            .foregroundStyle(Palette.ink)
                                        Text(entry.stageDisplay)
                                            .font(TypeScale.micro)
                                            .foregroundStyle(entry.style.color)
                                    }
                                }
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

    private var stageFilter: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                StageChip(label: "All stages", color: Palette.inkMuted, isSelected: model.stage == nil) {
                    model.stage = nil
                    Task { await model.load() }
                }
                ForEach(FunnelStageStyle.allCases, id: \.self) { stage in
                    StageChip(
                        label: stage.shortLabel,
                        color: stage.color,
                        isSelected: model.stage == stage.rawValue
                    ) {
                        model.stage = stage.rawValue
                        Task { await model.load() }
                    }
                }
            }
        }
    }
}

struct StageChip: View {
    let label: String
    let color: Color
    let isSelected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Text(label)
                .font(TypeScale.caption)
                .foregroundStyle(isSelected ? .white : color)
                .padding(.horizontal, 12)
                .padding(.vertical, 7)
                .background(isSelected ? color : color.opacity(0.12), in: Capsule())
        }
        .buttonStyle(.plain)
    }
}
