import SwiftUI

// MARK: - Pipeline rail
//
// The home screen's one bold element: the whole pipeline as a single bar,
// segmented by peso value across Micro Image's four named funnel stages. It
// answers "where is my money sitting?" without reading a number. Everything
// around it stays quiet.

struct PipelineRail: View {
    let stages: [FunnelStageSummary]
    let totalValue: Double

    private var segments: [FunnelStageSummary] {
        stages.filter { $0.value > 0 }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            VStack(alignment: .leading, spacing: 2) {
                Text("Pipeline")
                    .font(TypeScale.caption)
                    .foregroundStyle(Palette.inkMuted)
                Text(Format.currency(totalValue))
                    .font(TypeScale.figure(32))
                    .tracking(-0.8)
                    .foregroundStyle(Palette.ink)
            }

            if segments.isEmpty {
                RoundedRectangle(cornerRadius: 5)
                    .fill(Palette.hairline)
                    .frame(height: 10)
                Text("No deals in the funnel yet.")
                    .font(TypeScale.caption)
                    .foregroundStyle(Palette.inkMuted)
            } else {
                GeometryReader { geometry in
                    HStack(spacing: 2) {
                        ForEach(segments) { stage in
                            Capsule()
                                .fill(stage.style.color)
                                .frame(width: width(for: stage, in: geometry.size.width))
                        }
                    }
                }
                .frame(height: 10)

                // Legend doubles as the per-stage readout, so the bar needs no
                // labels of its own.
                VStack(spacing: 10) {
                    ForEach(stages) { stage in
                        HStack(spacing: 10) {
                            Circle()
                                .fill(stage.style.color)
                                .frame(width: 8, height: 8)
                            Text(stage.label)
                                .font(TypeScale.body)
                                .foregroundStyle(Palette.ink)
                            Spacer(minLength: 8)
                            Text("\(stage.count)")
                                .font(TypeScale.caption.monospacedDigit())
                                .foregroundStyle(Palette.inkFaint)
                            Text(Format.compactCurrency(stage.value))
                                .font(TypeScale.figureSmall(15))
                                .foregroundStyle(Palette.ink)
                        }
                    }
                }
            }
        }
        .padding(Metrics.gutter)
        .background(Palette.surface, in: RoundedRectangle(cornerRadius: Metrics.cardRadius))
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Pipeline total \(Format.currency(totalValue)) across \(stages.count) stages")
    }

    private func width(for stage: FunnelStageSummary, in total: CGFloat) -> CGFloat {
        let sum = segments.reduce(0) { $0 + $1.value }
        guard sum > 0 else { return 0 }
        let spacing = CGFloat(max(0, segments.count - 1)) * 2
        let available = max(0, total - spacing)
        // Floor each segment so a small stage stays visible rather than
        // collapsing to a sliver.
        return max(6, available * CGFloat(stage.value / sum))
    }
}

// MARK: - Action prompts
//
// Only shown when the count is non-zero. Elevation is reserved for things that
// want a decision, so a raised surface always means "this needs you".

struct ActionPrompt: View {
    let count: Int
    let title: String
    let subtitle: String
    let systemImage: String

    var body: some View {
        HStack(spacing: 14) {
            ZStack {
                Circle().fill(Palette.brand.opacity(0.1))
                Image(systemName: systemImage)
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundStyle(Palette.brand)
            }
            .frame(width: 40, height: 40)

            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(TypeScale.rowTitle)
                    .foregroundStyle(Palette.ink)
                Text(subtitle)
                    .font(TypeScale.caption)
                    .foregroundStyle(Palette.inkMuted)
            }

            Spacer(minLength: 8)

            Text("\(count)")
                .font(TypeScale.figureSmall(18))
                .foregroundStyle(Palette.brand)
            Image(systemName: "chevron.right")
                .font(.system(size: 12, weight: .semibold))
                .foregroundStyle(Palette.inkFaint)
        }
        .padding(16)
        .background(Palette.surface, in: RoundedRectangle(cornerRadius: Metrics.cardRadius))
    }
}

// MARK: - Structure

struct SectionHeading: View {
    let title: String
    var action: (title: String, handler: () -> Void)?

    var body: some View {
        HStack(alignment: .firstTextBaseline) {
            Text(title)
                .font(TypeScale.sectionTitle)
                .foregroundStyle(Palette.ink)
            Spacer()
            if let action {
                Button(action.title, action: action.handler)
                    .font(TypeScale.caption)
                    .foregroundStyle(Palette.brand)
            }
        }
    }
}

/// A flat list row. Rows use hairlines rather than nesting each item in its own
/// card, so a long list stays scannable.
struct PlainRow<Trailing: View>: View {
    let title: String
    let subtitle: String?
    var accent: Color?
    @ViewBuilder var trailing: () -> Trailing

    var body: some View {
        HStack(spacing: 12) {
            if let accent {
                RoundedRectangle(cornerRadius: 2)
                    .fill(accent)
                    .frame(width: 3, height: 34)
            }
            VStack(alignment: .leading, spacing: 3) {
                Text(title)
                    .font(TypeScale.rowTitle)
                    .foregroundStyle(Palette.ink)
                    .lineLimit(1)
                if let subtitle {
                    Text(subtitle)
                        .font(TypeScale.caption)
                        .foregroundStyle(Palette.inkMuted)
                        .lineLimit(1)
                }
            }
            Spacer(minLength: 8)
            trailing()
        }
        .padding(.vertical, 12)
        .contentShape(Rectangle())
    }
}

extension PlainRow where Trailing == EmptyView {
    init(title: String, subtitle: String?, accent: Color? = nil) {
        self.init(title: title, subtitle: subtitle, accent: accent) { EmptyView() }
    }
}

struct StatusTag: View {
    let text: String
    let color: Color

    var body: some View {
        Text(text)
            .font(TypeScale.micro)
            .foregroundStyle(color)
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(color.opacity(0.12), in: Capsule())
    }
}

/// Maps the server's status vocabulary onto the palette. Kept in one place so
/// "approved" is the same green on every screen.
enum StatusPalette {
    static func color(for status: String?) -> Color {
        switch (status ?? "").lowercased() {
        case "approved", "completed", "won", "sent":
            return Palette.positive
        case "pending", "planned", "in_progress", "scheduled", "draft":
            return Palette.warning
        case "rejected", "cancelled", "lost", "failed":
            return Palette.critical
        default:
            return Palette.inkMuted
        }
    }

    static func label(for status: String?) -> String {
        guard let status, !status.isEmpty else { return "Unknown" }
        return status
            .replacingOccurrences(of: "_", with: " ")
            .capitalized
    }
}

// MARK: - States

struct LoadingState: View {
    var body: some View {
        VStack {
            ProgressView().tint(Palette.brand)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

/// An empty screen is an invitation to act, so it always names the next step.
struct EmptyState: View {
    let title: String
    let message: String
    var systemImage: String = "tray"
    var action: (title: String, handler: () -> Void)?

    var body: some View {
        VStack(spacing: 10) {
            Image(systemName: systemImage)
                .font(.system(size: 28, weight: .light))
                .foregroundStyle(Palette.inkFaint)
                .padding(.bottom, 2)
            Text(title)
                .font(TypeScale.sectionTitle)
                .foregroundStyle(Palette.ink)
            Text(message)
                .font(TypeScale.body)
                .foregroundStyle(Palette.inkMuted)
                .multilineTextAlignment(.center)
                .frame(maxWidth: 280)
            if let action {
                Button(action.title, action: action.handler)
                    .buttonStyle(PrimaryButtonStyle())
                    .padding(.top, 6)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(Metrics.gutter)
    }
}

struct ErrorState: View {
    let message: String
    let retry: () -> Void

    var body: some View {
        VStack(spacing: 10) {
            Image(systemName: "exclamationmark.triangle")
                .font(.system(size: 26, weight: .light))
                .foregroundStyle(Palette.critical)
            Text(message)
                .font(TypeScale.body)
                .foregroundStyle(Palette.ink)
                .multilineTextAlignment(.center)
                .frame(maxWidth: 300)
            Button("Try again", action: retry)
                .buttonStyle(SecondaryButtonStyle())
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(Metrics.gutter)
    }
}

// MARK: - Buttons

struct PrimaryButtonStyle: ButtonStyle {
    @Environment(\.isEnabled) private var isEnabled

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 16, weight: .semibold))
            .foregroundStyle(.white)
            .frame(maxWidth: .infinity)
            .frame(height: 50)
            .background(
                Palette.brand.opacity(isEnabled ? (configuration.isPressed ? 0.85 : 1) : 0.4),
                in: RoundedRectangle(cornerRadius: Metrics.controlRadius)
            )
    }
}

struct SecondaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 16, weight: .medium))
            .foregroundStyle(Palette.ink)
            .frame(maxWidth: .infinity)
            .frame(height: 48)
            .background(Palette.surface, in: RoundedRectangle(cornerRadius: Metrics.controlRadius))
            .overlay(
                RoundedRectangle(cornerRadius: Metrics.controlRadius)
                    .stroke(Palette.hairline, lineWidth: 1)
            )
            .opacity(configuration.isPressed ? 0.7 : 1)
    }
}

// MARK: - Containers

/// Groups rows on a card with hairline separators between them.
struct RowCard<Content: View>: View {
    @ViewBuilder var content: () -> Content

    var body: some View {
        VStack(spacing: 0) { content() }
            .padding(.horizontal, 16)
            .background(Palette.surface, in: RoundedRectangle(cornerRadius: Metrics.cardRadius))
    }
}

struct Hairline: View {
    var body: some View {
        Rectangle()
            .fill(Palette.hairline)
            .frame(height: 1)
    }
}

/// Standard page chrome: canvas background and consistent gutters.
struct ScreenScroll<Content: View>: View {
    @ViewBuilder var content: () -> Content

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                content()
            }
            .padding(.horizontal, Metrics.gutter)
            .padding(.vertical, 16)
        }
        .background(Palette.canvas)
    }
}
