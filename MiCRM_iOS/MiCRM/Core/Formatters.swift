import Foundation

enum Format {
    private static let peso: NumberFormatter = {
        let f = NumberFormatter()
        f.numberStyle = .currency
        f.currencyCode = "PHP"
        f.currencySymbol = "₱"
        f.maximumFractionDigits = 0
        return f
    }()

    static func currency(_ value: Double, code: String = "PHP") -> String {
        peso.currencyCode = code
        peso.currencySymbol = code == "PHP" ? "₱" : code + " "
        return peso.string(from: NSNumber(value: value)) ?? "\(value)"
    }

    /// Compact form for tiles where the exact peso is noise: ₱1.3M, ₱850K.
    ///
    /// Rounds half away from zero rather than letting `%f` round half-to-even —
    /// ₱1,250,000 reading as "₱1.2M" understates a figure someone is using to
    /// make a call.
    static func compactCurrency(_ value: Double, code: String = "PHP") -> String {
        let symbol = code == "PHP" ? "₱" : code + " "
        switch abs(value) {
        case 1_000_000...:
            let millions = ((value / 1_000_000) * 10).rounded() / 10
            return String(format: "%@%.1fM", symbol, millions)
        case 10_000...:
            return String(format: "%@%.0fK", symbol, (value / 1_000).rounded())
        default:
            return currency(value, code: code)
        }
    }

    private static let dayAndTime: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "d MMM, h:mm a"
        return f
    }()

    private static let timeOnly: DateFormatter = {
        let f = DateFormatter()
        f.timeStyle = .short
        f.dateStyle = .none
        return f
    }()

    private static let dayOnly: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "d MMM yyyy"
        return f
    }()

    /// "Today, 2:30 PM" reads faster than a date when the item is imminent,
    /// which is the common case on the schedule list.
    static func schedule(_ date: Date?) -> String {
        guard let date else { return "Not scheduled" }
        let calendar = Calendar.current
        if calendar.isDateInToday(date) { return "Today, " + timeOnly.string(from: date) }
        if calendar.isDateInTomorrow(date) { return "Tomorrow, " + timeOnly.string(from: date) }
        if calendar.isDateInYesterday(date) { return "Yesterday, " + timeOnly.string(from: date) }
        return dayAndTime.string(from: date)
    }

    static func day(_ date: Date?) -> String {
        guard let date else { return "—" }
        return dayOnly.string(from: date)
    }

    /// Parses the ISO strings the API returns for created/reviewed timestamps.
    static func dayFromISO(_ raw: String?) -> String {
        guard let raw, let date = DateParsing.parse(raw) else { return "—" }
        return dayOnly.string(from: date)
    }

    static func initials(from name: String) -> String {
        let parts = name.split(separator: " ").prefix(2)
        let letters = parts.compactMap { $0.first.map(String.init) }
        return letters.isEmpty ? "?" : letters.joined().uppercased()
    }

    /// The API takes naive local datetimes for scheduling.
    static func apiDateTime(_ date: Date) -> String {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
        return f.string(from: date)
    }
}
