import SwiftUI

// MARK: - Raise a request

@MainActor
@Observable
final class NewCustomerRequestModel {
    var choices: CustomerChoices?
    var isSaving = false

    func load() async {
        choices = try? await APIClient.shared.customerChoices()
    }

    func submit(_ request: NewCustomerRequest) async -> String? {
        isSaving = true
        defer { isSaving = false }
        do {
            _ = try await APIClient.shared.submitCustomerRequest(request)
            return nil
        } catch {
            return (error as? APIError)?.errorDescription ?? error.localizedDescription
        }
    }
}

/// Salespeople don't create customers directly — they raise a request that a
/// manager approves. The copy says so up front so the outcome isn't a surprise.
struct NewCustomerRequestView: View {
    @Environment(\.dismiss) private var dismiss
    @State private var model = NewCustomerRequestModel()

    @State private var companyName = ""
    @State private var contactName = ""
    @State private var position = ""
    @State private var email = ""
    @State private var phone = ""
    @State private var address = ""
    @State private var industry: String?
    @State private var territory: String?
    @State private var errorMessage: String?
    @State private var didSubmit = false

    private var canSubmit: Bool {
        !companyName.trimmingCharacters(in: .whitespaces).isEmpty
            && !contactName.trimmingCharacters(in: .whitespaces).isEmpty
            && email.contains("@")
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                if didSubmit {
                    submitted
                } else {
                    Text("Your manager reviews this before the customer is added. You'll see the outcome under My requests.")
                        .font(TypeScale.body)
                        .foregroundStyle(Palette.inkMuted)
                        .fixedSize(horizontal: false, vertical: true)

                    LabeledField(label: "Company", text: $companyName, placeholder: "Registered company name")
                    LabeledField(label: "Contact person", text: $contactName, placeholder: "Full name")
                    LabeledField(label: "Position", text: $position, placeholder: "e.g. IT Manager")
                    LabeledField(label: "Email", text: $email, placeholder: "name@company.com")
                        .emailKeyboard()
                        .autocorrectionDisabled()
                    LabeledField(label: "Phone", text: $phone, placeholder: "Landline or mobile")
                        .phoneKeyboard()
                    LabeledField(label: "Address", text: $address, placeholder: "Office address")

                    if let choices = model.choices {
                        RowCard {
                            Picker("Industry", selection: $industry) {
                                Text("Not set").tag(Optional<String>.none)
                                ForEach(choices.industries) { option in
                                    Text(option.label).tag(Optional(option.value))
                                }
                            }
                            .padding(.vertical, 6)
                            Hairline()
                            Picker("Territory", selection: $territory) {
                                Text("Not set").tag(Optional<String>.none)
                                ForEach(choices.territories) { option in
                                    Text(option.label).tag(Optional(option.value))
                                }
                            }
                            .padding(.vertical, 6)
                        }
                    }

                    if let errorMessage {
                        Text(errorMessage)
                            .font(TypeScale.caption)
                            .foregroundStyle(Palette.critical)
                    }

                    Button(action: submit) {
                        if model.isSaving {
                            ProgressView().tint(.white)
                        } else {
                            Text("Send for approval")
                        }
                    }
                    .buttonStyle(PrimaryButtonStyle())
                    .disabled(model.isSaving || !canSubmit)
                }
            }
            .padding(Metrics.gutter)
        }
        .background(Palette.canvas)
        .navigationTitle("New customer")
        .inlineNavigationTitle()
        .toolbar {
            ToolbarItem {
                Button(didSubmit ? "Done" : "Cancel") { dismiss() }
            }
        }
        .task { await model.load() }
    }

    private var submitted: some View {
        VStack(spacing: 10) {
            Image(systemName: "paperplane")
                .font(.system(size: 28, weight: .light))
                .foregroundStyle(Palette.positive)
            Text("Request sent")
                .font(TypeScale.sectionTitle)
                .foregroundStyle(Palette.ink)
            Text("\(companyName) is now waiting for approval.")
                .font(TypeScale.body)
                .foregroundStyle(Palette.inkMuted)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 40)
    }

    private func submit() {
        errorMessage = nil
        Task {
            let request = NewCustomerRequest(
                companyName: companyName.trimmingCharacters(in: .whitespaces),
                contactPersonName: contactName.trimmingCharacters(in: .whitespaces),
                contactPersonPosition: position.isEmpty ? nil : position,
                email: email.trimmingCharacters(in: .whitespaces),
                phoneNumber: phone.isEmpty ? nil : phone,
                address: address.isEmpty ? nil : address,
                industry: industry,
                territory: territory
            )
            if let error = await model.submit(request) {
                errorMessage = error
            } else {
                didSubmit = true
            }
        }
    }
}

// MARK: - Request queues

@MainActor
@Observable
final class CustomerRequestListModel {
    var requests: [CustomerRequest] = []
    var isLoading = true
    var errorMessage: String?
    var decidingId: Int?

    let reviewing: Bool

    init(reviewing: Bool) { self.reviewing = reviewing }

    func load() async {
        errorMessage = nil
        do {
            requests = reviewing
                ? try await APIClient.shared.pendingCustomerRequests()
                : try await APIClient.shared.myCustomerRequests()
        } catch {
            errorMessage = (error as? APIError)?.errorDescription ?? error.localizedDescription
        }
        isLoading = false
    }

    func decide(_ request: CustomerRequest, approve: Bool) async {
        decidingId = request.id
        defer { decidingId = nil }
        do {
            try await APIClient.shared.decideCustomerRequest(id: request.id, approve: approve)
            await load()
        } catch {
            errorMessage = (error as? APIError)?.errorDescription ?? error.localizedDescription
        }
    }
}

struct PendingCustomerRequestsView: View {
    @State private var model = CustomerRequestListModel(reviewing: true)

    var body: some View {
        CustomerRequestList(
            model: model,
            title: "Requests to review",
            emptyTitle: "Nothing to review",
            emptyMessage: "New customer requests from your team will appear here."
        )
    }
}

struct MyCustomerRequestsView: View {
    @State private var model = CustomerRequestListModel(reviewing: false)

    var body: some View {
        CustomerRequestList(
            model: model,
            title: "My requests",
            emptyTitle: "No requests yet",
            emptyMessage: "Customers you ask to have added will be tracked here until they're approved."
        )
    }
}

private struct CustomerRequestList: View {
    @Bindable var model: CustomerRequestListModel
    let title: String
    let emptyTitle: String
    let emptyMessage: String

    var body: some View {
        Group {
            if model.isLoading {
                LoadingState()
            } else if let message = model.errorMessage, model.requests.isEmpty {
                ErrorState(message: message) { Task { await model.load() } }
            } else if model.requests.isEmpty {
                EmptyState(title: emptyTitle, message: emptyMessage, systemImage: "person.badge.plus")
            } else {
                ScreenScroll {
                    ForEach(model.requests) { request in
                        RequestCard(
                            request: request,
                            canDecide: model.reviewing && request.status == "pending",
                            isDeciding: model.decidingId == request.id,
                            onDecide: { approve in
                                Task { await model.decide(request, approve: approve) }
                            }
                        )
                    }
                }
            }
        }
        .background(Palette.canvas)
        .navigationTitle(title)
        .inlineNavigationTitle()
        .task { await model.load() }
        .refreshable { await model.load() }
    }
}

private struct RequestCard: View {
    let request: CustomerRequest
    let canDecide: Bool
    let isDeciding: Bool
    let onDecide: (Bool) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 3) {
                    Text(request.companyName)
                        .font(TypeScale.rowTitle)
                        .foregroundStyle(Palette.ink)
                    Text(request.contactPersonName)
                        .font(TypeScale.caption)
                        .foregroundStyle(Palette.inkMuted)
                }
                Spacer(minLength: 8)
                StatusTag(
                    text: StatusPalette.label(for: request.status),
                    color: StatusPalette.color(for: request.status)
                )
            }

            Text(request.email)
                .font(TypeScale.caption)
                .foregroundStyle(Palette.inkMuted)

            HStack(spacing: 6) {
                if let requester = request.requestedByName {
                    Text(requester)
                }
                Text(Format.dayFromISO(request.createdAt))
            }
            .font(TypeScale.caption)
            .foregroundStyle(Palette.inkFaint)

            if let notes = request.decisionNotes, !notes.isEmpty {
                Text(notes)
                    .font(TypeScale.caption)
                    .foregroundStyle(Palette.inkMuted)
                    .padding(10)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Palette.canvas, in: RoundedRectangle(cornerRadius: 8))
            }

            if canDecide {
                HStack(spacing: 10) {
                    Button("Approve") { onDecide(true) }
                        .buttonStyle(PrimaryButtonStyle())
                    Button("Reject") { onDecide(false) }
                        .buttonStyle(SecondaryButtonStyle())
                }
                .disabled(isDeciding)
                .opacity(isDeciding ? 0.5 : 1)
            }
        }
        .padding(Metrics.gutter)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Palette.surface, in: RoundedRectangle(cornerRadius: Metrics.cardRadius))
    }
}
