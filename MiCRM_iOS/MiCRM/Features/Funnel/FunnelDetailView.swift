import SwiftUI

/// Read-only detail for a single Sales Funnel entry. Reached by tapping a row in
/// FunnelView. The list already loads the full entry, so this view renders the
/// passed-in model directly — no extra network call. Mirrors the Android
/// FunnelDetailScreen layout (header, requirement, figures, customer).
struct FunnelDetailView: View {
    let entry: FunnelEntry

    private var retailValue: Double { Double(entry.retail) ?? 0 }
    private var costValue: Double? { Double(entry.cost) }
    private var profitValue: Double? {
        guard let costValue else { return nil }
        return retailValue - costValue
    }

    var body: some View {
        ScreenScroll {
            header

            if !entry.requirementDescription.isEmpty {
                VStack(alignment: .leading, spacing: 10) {
                    SectionHeading(title: "Requirement")
                    RowCard {
                        Text(entry.requirementDescription)
                            .font(TypeScale.body)
                            .foregroundStyle(Palette.ink)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .fixedSize(horizontal: false, vertical: true)
                            .padding(.vertical, 14)
                    }
                }
            }

            figures

            if let name = entry.customerName, !name.isEmpty, name != "Unknown" {
                VStack(alignment: .leading, spacing: 10) {
                    SectionHeading(title: "Customer")
                    RowCard {
                        Text(name)
                            .font(TypeScale.rowTitle)
                            .foregroundStyle(Palette.ink)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(.vertical, 14)
                    }
                }
            }
        }
        .background(Palette.canvas)
        .navigationTitle(entry.companyName)
        .inlineNavigationTitle()
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text(entry.companyName)
                .font(.system(size: 23, weight: .bold))
                .tracking(-0.4)
                .foregroundStyle(Palette.ink)
                .fixedSize(horizontal: false, vertical: true)

            Text(Format.currency(retailValue))
                .font(TypeScale.figure(32))
                .tracking(-0.8)
                .foregroundStyle(Palette.ink)

            HStack(spacing: 8) {
                StatusTag(text: entry.stageDisplay, color: entry.style.color)
                if let probability = entry.probability {
                    StatusTag(text: "\(probability)% win", color: Palette.inkMuted)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(Metrics.gutter)
        .background(Palette.surface, in: RoundedRectangle(cornerRadius: Metrics.cardRadius))
    }

    private var figures: some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionHeading(title: "Figures")
            RowCard {
                if let costValue {
                    MetricRow(label: "Cost", value: Format.currency(costValue))
                    Hairline()
                }
                MetricRow(label: "SRP (Retail)", value: Format.currency(retailValue))
                if let profitValue {
                    Hairline()
                    MetricRow(label: "Profit", value: Format.currency(profitValue))
                }
                if let probability = entry.probability {
                    Hairline()
                    MetricRow(label: "Win probability", value: "\(probability)%")
                }
            }
        }
    }
}
