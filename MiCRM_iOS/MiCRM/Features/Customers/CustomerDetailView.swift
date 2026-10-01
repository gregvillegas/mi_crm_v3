import SwiftUI

@MainActor
@Observable
final class CustomerDetailModel {
    var customer: CustomerDetail?
    var activities: [SalesActivity] = []
    var errorMessage: String?
    var isLoading = true

    func load(id: Int) async {
        errorMessage = nil
        do {
            async let detail = APIClient.shared.customer(id: id)
            async let recent = APIClient.shared.activities(customerId: id)
            customer = try await detail
            activities = try await recent
        } catch {
            errorMessage = (error as? APIError)?.errorDescription ?? error.localizedDescription
        }
        isLoading = false
    }
}

struct CustomerDetailView: View {
    let customerId: Int
    @State private var model = CustomerDetailModel()

    var body: some View {
        Group {
            if model.isLoading {
                LoadingState()
            } else if let message = model.errorMessage, model.customer == nil {
                ErrorState(message: message) { Task { await model.load(id: customerId) } }
            } else if let customer = model.customer {
                content(customer)
            }
        }
        .background(Palette.canvas)
        .navigationTitle(model.customer?.companyName ?? "Customer")
        .inlineNavigationTitle()
        .task { await model.load(id: customerId) }
    }

    private func content(_ customer: CustomerDetail) -> some View {
        ScreenScroll {
            header(customer)

            contactActions(customer)

            if !customer.contacts.isEmpty {
                VStack(alignment: .leading, spacing: 10) {
                    SectionHeading(title: "Contacts")
                    RowCard {
                        ForEach(Array(customer.contacts.enumerated()), id: \.offset) { index, contact in
                            if index > 0 { Hairline() }
                            PlainRow(
                                title: contact.name,
                                subtitle: [contact.position, contact.email, contact.phone]
                                    .compactMap { $0 }
                                    .filter { !$0.isEmpty }
                                    .joined(separator: " · ")
                            ) {
                                if contact.isPrimary {
                                    StatusTag(text: "Primary", color: Palette.positive)
                                }
                            }
                        }
                    }
                }
            }

            details(customer)

            recentActivity
        }
    }

    private func header(_ customer: CustomerDetail) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(customer.companyName)
                .font(.system(size: 24, weight: .bold))
                .tracking(-0.4)
                .foregroundStyle(Palette.ink)

            HStack(spacing: 8) {
                if customer.isMillionaireAccount {
                    StatusTag(text: "Key account", color: Palette.positive)
                }
                if customer.autoInactiveFlag {
                    StatusTag(text: "No recent activity", color: Palette.warning)
                }
                if !customer.isActive {
                    StatusTag(text: "Inactive", color: Palette.critical)
                }
            }
        }
    }

    // The three things someone needs while walking into a meeting.
    private func contactActions(_ customer: CustomerDetail) -> some View {
        HStack(spacing: 10) {
            if let phone = customer.phoneNumber, !phone.isEmpty,
               let url = URL(string: "tel://\(phone.filter { $0.isNumber || $0 == "+" })") {
                Link(destination: url) {
                    QuickAction(systemImage: "phone.fill", label: "Call")
                }
            }
            if !customer.email.isEmpty, let url = URL(string: "mailto:\(customer.email)") {
                Link(destination: url) {
                    QuickAction(systemImage: "envelope.fill", label: "Email")
                }
            }
            NavigationLink {
                ActivityCreateView(preselectedCustomerId: customer.id)
            } label: {
                QuickAction(systemImage: "plus", label: "Log activity")
            }
            .buttonStyle(.plain)
        }
    }

    private func details(_ customer: CustomerDetail) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionHeading(title: "Details")
            RowCard {
                DetailRow(label: "Contact", value: customer.contactPersonName)
                Hairline()
                DetailRow(label: "Position", value: customer.contactPersonPosition)
                Hairline()
                DetailRow(label: "Email", value: customer.email)
                Hairline()
                DetailRow(label: "Phone", value: customer.phoneNumber)
                Hairline()
                DetailRow(label: "Industry", value: customer.industry)
                Hairline()
                DetailRow(label: "Territory", value: customer.territory)
                Hairline()
                DetailRow(label: "Address", value: customer.address)
                Hairline()
                DetailRow(label: "Account manager", value: customer.salespersonName)
            }
        }
    }

    @ViewBuilder
    private var recentActivity: some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionHeading(title: "Activity")
            if model.activities.isEmpty {
                RowCard {
                    Text("No activity logged against this customer yet.")
                        .font(TypeScale.body)
                        .foregroundStyle(Palette.inkMuted)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.vertical, 16)
                }
            } else {
                RowCard {
                    ForEach(Array(model.activities.prefix(8).enumerated()), id: \.element.id) { index, activity in
                        if index > 0 { Hairline() }
                        PlainRow(
                            title: activity.title,
                            subtitle: Format.schedule(activity.scheduledStart)
                        ) {
                            StatusTag(
                                text: activity.statusDisplay ?? StatusPalette.label(for: activity.status),
                                color: StatusPalette.color(for: activity.status)
                            )
                        }
                    }
                }
            }
        }
    }
}

struct QuickAction: View {
    let systemImage: String
    let label: String

    var body: some View {
        VStack(spacing: 6) {
            Image(systemName: systemImage)
                .font(.system(size: 15, weight: .semibold))
            Text(label)
                .font(TypeScale.micro)
        }
        .foregroundStyle(Palette.brand)
        .frame(maxWidth: .infinity)
        .padding(.vertical, 14)
        .background(Palette.surface, in: RoundedRectangle(cornerRadius: Metrics.controlRadius))
    }
}

struct DetailRow: View {
    let label: String
    let value: String?

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Text(label)
                .font(TypeScale.body)
                .foregroundStyle(Palette.inkMuted)
                .frame(width: 128, alignment: .leading)
            Text(value?.isEmpty == false ? value! : "—")
                .font(TypeScale.body)
                .foregroundStyle(Palette.ink)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(.vertical, 12)
    }
}
