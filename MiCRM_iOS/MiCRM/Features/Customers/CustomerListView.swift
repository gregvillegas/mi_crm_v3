import SwiftUI

@MainActor
@Observable
final class CustomerListModel {
    var customers: [CustomerSummary] = []
    var isLoading = false
    var errorMessage: String?
    var search = ""
    var mineOnly = false

    private var searchTask: Task<Void, Never>?

    func load() async {
        if customers.isEmpty { isLoading = true }
        errorMessage = nil
        do {
            customers = try await APIClient.shared.customers(
                search: search.isEmpty ? nil : search,
                mineOnly: mineOnly
            )
        } catch {
            errorMessage = (error as? APIError)?.errorDescription ?? error.localizedDescription
        }
        isLoading = false
    }

    /// Debounced so typing doesn't fire a request per keystroke.
    func searchChanged() {
        searchTask?.cancel()
        searchTask = Task {
            try? await Task.sleep(for: .milliseconds(300))
            guard !Task.isCancelled else { return }
            await load()
        }
    }
}

struct CustomerListView: View {
    @State private var model = CustomerListModel()
    @State private var showingNewRequest = false

    var body: some View {
        Group {
            if model.isLoading {
                LoadingState()
            } else if let message = model.errorMessage, model.customers.isEmpty {
                ErrorState(message: message) { Task { await model.load() } }
            } else if model.customers.isEmpty {
                EmptyState(
                    title: model.search.isEmpty ? "No customers yet" : "No matches",
                    message: model.search.isEmpty
                        ? "Customers assigned to you will appear here."
                        : "Nothing matched “\(model.search)”. Try a company name, contact, or phone number.",
                    systemImage: "building.2",
                    action: model.search.isEmpty
                        ? (title: "Request a customer", handler: { showingNewRequest = true })
                        : nil
                )
            } else {
                list
            }
        }
        .background(Palette.canvas)
        .navigationTitle("Customers")
        .searchable(text: Binding(
            get: { model.search },
            set: { model.search = $0; model.searchChanged() }
        ), prompt: "Company, contact, or phone")
        .toolbar {
            ToolbarItem {
                Button {
                    showingNewRequest = true
                } label: {
                    Image(systemName: "plus")
                }
                .accessibilityLabel("Request a new customer")
            }
        }
        .sheet(isPresented: $showingNewRequest) {
            NavigationStack { NewCustomerRequestView() }
        }
        .task { await model.load() }
        .refreshable { await model.load() }
    }

    private var list: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                Picker("Scope", selection: Binding(
                    get: { model.mineOnly },
                    set: { model.mineOnly = $0; Task { await model.load() } }
                )) {
                    Text("All I can see").tag(false)
                    Text("Assigned to me").tag(true)
                }
                .pickerStyle(.segmented)

                RowCard {
                    ForEach(Array(model.customers.enumerated()), id: \.element.id) { index, customer in
                        if index > 0 { Hairline() }
                        NavigationLink {
                            CustomerDetailView(customerId: customer.id)
                        } label: {
                            CustomerRow(customer: customer)
                        }
                        .buttonStyle(.plain)
                    }
                }

                Text("\(model.customers.count) \(model.customers.count == 1 ? "customer" : "customers")")
                    .font(TypeScale.caption)
                    .foregroundStyle(Palette.inkFaint)
                    .frame(maxWidth: .infinity, alignment: .center)
            }
            .padding(.horizontal, Metrics.gutter)
            .padding(.vertical, 16)
        }
        .background(Palette.canvas)
    }
}

struct CustomerRow: View {
    let customer: CustomerSummary

    var body: some View {
        HStack(spacing: 12) {
            Monogram(text: Format.initials(from: customer.companyName))

            VStack(alignment: .leading, spacing: 3) {
                Text(customer.companyName)
                    .font(TypeScale.rowTitle)
                    .foregroundStyle(Palette.ink)
                    .lineLimit(1)
                Text(customer.contactPersonName)
                    .font(TypeScale.caption)
                    .foregroundStyle(Palette.inkMuted)
                    .lineLimit(1)
            }

            Spacer(minLength: 8)

            if customer.isMillionaireAccount {
                StatusTag(text: "Key", color: Palette.positive)
            } else if customer.autoInactiveFlag {
                StatusTag(text: "Dormant", color: Palette.warning)
            }
        }
        .padding(.vertical, 11)
        .contentShape(Rectangle())
    }
}

struct Monogram: View {
    let text: String

    var body: some View {
        Text(text)
            .font(.system(size: 13, weight: .semibold))
            .foregroundStyle(Palette.inkMuted)
            .frame(width: 36, height: 36)
            .background(Palette.canvas, in: RoundedRectangle(cornerRadius: 9))
    }
}
