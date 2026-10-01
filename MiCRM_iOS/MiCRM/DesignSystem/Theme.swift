import SwiftUI

// MARK: - Palette
//
// The accent system is Micro Image's own vocabulary. The CRM names its four
// pipeline stages by colour — Pink, Yellow, Green and Blue Funnel — so those
// colours identify a deal's stage everywhere it appears, and brand red is held
// back for identity and primary actions. Colour therefore always means
// something: stage colour = where the money is, red = act.

enum Palette {
    static let ink = Color(hex: 0x1B1F27)
    static let inkMuted = Color(hex: 0x5C6675)
    static let inkFaint = Color(hex: 0x8A93A1)

    static let canvas = Color(hex: 0xF1F3F7)
    static let surface = Color.white
    static let hairline = Color(hex: 0xDFE3EA)

    /// MiRed. Identity and primary/destructive actions only — never decoration.
    static let brand = Color(hex: 0xA11313)

    static let positive = Color(hex: 0x1B7A4B)
    static let warning = Color(hex: 0xC77700)
    static let critical = Color(hex: 0xB3261E)
}

/// The four funnel stages, in pipeline order.
enum FunnelStageStyle: String, CaseIterable {
    case quoted, closable, project, services

    /// Yellow is darkened to #C77700 so it still passes contrast on white —
    /// a literal yellow fails as a text/edge colour.
    var color: Color {
        switch self {
        case .quoted: return Color(hex: 0xD81B60)
        case .closable: return Color(hex: 0xC77700)
        case .project: return Color(hex: 0x1B7A4B)
        case .services: return Color(hex: 0x0056B3)
        }
    }

    var shortLabel: String {
        switch self {
        case .quoted: return "Quoted"
        case .closable: return "Closable"
        case .project: return "Project"
        case .services: return "Services"
        }
    }

    static func from(_ raw: String) -> FunnelStageStyle {
        FunnelStageStyle(rawValue: raw) ?? .quoted
    }
}

// MARK: - Type scale
//
// SF Pro throughout, so Dynamic Type works for free. The deliberate choice is
// numerics: this app is mostly figures stacked vertically, and monospaced
// digits keep them aligned when a salesperson scans a column of amounts.

enum TypeScale {
    /// Large figures — pipeline totals, amounts on a detail screen.
    static func figure(_ size: CGFloat = 30) -> Font {
        .system(size: size, weight: .bold, design: .default).monospacedDigit()
    }

    /// Figures inside rows and tiles.
    static func figureSmall(_ size: CGFloat = 17) -> Font {
        .system(size: size, weight: .semibold).monospacedDigit()
    }

    static let screenTitle = Font.system(size: 26, weight: .bold)
    static let sectionTitle = Font.system(size: 19, weight: .semibold)
    static let rowTitle = Font.system(size: 16, weight: .medium)
    static let body = Font.system(size: 15)
    static let caption = Font.system(size: 13)
    static let micro = Font.system(size: 11, weight: .medium)
}

// MARK: - Metrics

enum Metrics {
    static let gutter: CGFloat = 20
    static let rowSpacing: CGFloat = 14
    static let cardRadius: CGFloat = 14
    static let controlRadius: CGFloat = 10
}

// MARK: - Helpers

extension Color {
    init(hex: UInt32) {
        self.init(
            .sRGB,
            red: Double((hex >> 16) & 0xFF) / 255,
            green: Double((hex >> 8) & 0xFF) / 255,
            blue: Double(hex & 0xFF) / 255,
            opacity: 1
        )
    }
}
