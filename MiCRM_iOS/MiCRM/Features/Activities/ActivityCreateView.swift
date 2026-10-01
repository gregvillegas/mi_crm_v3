import SwiftUI

@MainActor
@Observable
final class ActivityCreateModel {
    var types: [ActivityType] = []
    var customers: [CustomerSummary] = []
    var isLoading = true
    var isSaving = false
    var errorMessage: String?

    func load() async {
        do {
            async let types = APIClient.shared.activityTypes()
            async let customers = APIClient.shared.customers()
            self.types = try await types
            self.customers = try await customers
        } catch {
            errorMessage = (error as? APIError)?.errorDescription ?? error.localizedDescription
        }
        isLoading = false
    }

    func save(_ activity: NewActivity) async -> String? {
        isSaving = true
        defer { isSaving = false }
        do {
            _ = try await APIClient.shared.createActivity(activity)
            return nil
        } catch {
            return (error as? APIError)?.errorDescription ?? error.localizedDescription
        }
    }
}

struct ActivityCreateView: View {
    var preselectedCustomerId: Int?

    @Environment(\.dismiss) private var dismiss
    @State private var model = ActivityCreateModel()

    @State private var title = ""
    @State private var notes = ""
    @State private var selectedType: ActivityType?
    @State private var selectedCustomerId: Int?
    @State private var priority = "medium"
    @State private var scheduledStart = Date().addingTimeInterval(3600)
    @State private var scheduledEnd = Date().addingTimeInterval(5400)
    @State private var errorMessage: String?

    private let priorities = [
        ("low", "Low"), ("medium", "Medium"), ("high", "High"), ("urgent", "Urgent"),
    ]

    var body: some View {
        Group {
            if model.isLoading {
                LoadingState()
            } else {
                form
            }
        }
        .background(Palette.canvas)
        .navigationTitle("Log activity")
        .inlineNavigationTitle()
        .toolbar {
            ToolbarItem {
                Button("Cancel") { dismiss() }
            }
        }
        .task {
            await model.load()
            selectedType = model.types.first
            selectedCustomerId = preselectedCustomerId
        }
    }

    private var form: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                LabeledField(label: "What happened", text: $title, placeholder: "e.g. Site visit and requirements walkthrough")

                RowCard {
                    Picker("Type", selection: $selectedType) {
                        ForEach(model.types) { type in
                            Text(type.name).tag(Optional(type))
                        }
                    }
                    .padding(.vertical, 6)

                    Hairline()

                    Picker("Customer", selection: $selectedCustomerId) {
                        Text("None").tag(Optional<Int>.none)
                        ForEach(model.customers) { customer in
                            Text(customer.companyName).tag(Optional(customer.id))
                        }
                    }
                    .padding(.vertical, 6)

                    Hairline()

                    Picker("Priority", selection: $priority) {
                        ForEach(priorities, id: \.0) { value, label in
                            Text(label).tag(value)
                        }
                    }
                    .padding(.vertical, 6)
                }

                RowCard {
                    DatePicker("Starts", selection: $scheduledStart)
                        .padding(.vertical, 8)
                    Hairline()
                    DatePicker("Ends", selection: $scheduledEnd, in: scheduledStart...)
                        .padding(.vertical, 8)
                }

                VStack(alignment: .leading, spacing: 6) {
                    Text("Notes")
                        .font(TypeScale.caption)
                        .foregroundStyle(Palette.inkMuted)
                    TextEditor(text: $notes)
                        .font(TypeScale.body)
                        .frame(height: 110)
                        .padding(8)
                        .background(Palette.surface, in: RoundedRectangle(cornerRadius: Metrics.controlRadius))
                        .overlay(
                            RoundedRectangle(cornerRadius: Metrics.controlRadius)
                                .stroke(Palette.hairline, lineWidth: 1)
                        )
                }

                if let errorMessage {
                    Text(errorMessage)
                        .font(TypeScale.caption)
                        .foregroundStyle(Palette.critical)
                }

                Button(action: save) {
                    if model.isSaving {
                        ProgressView().tint(.white)
                    } else {
                        Text("Save activity")
                    }
                }
                .buttonStyle(PrimaryButtonStyle())
                .disabled(model.isSaving || title.trimmingCharacters(in: .whitespaces).isEmpty || selectedType == nil)
            }
            .padding(Metrics.gutter)
        }
        .background(Palette.canvas)
    }

    private func save() {
        guard let type = selectedType else { return }
        errorMessage = nil
        Task {
            let activity = NewActivity(
                title: title.trimmingCharacters(in: .whitespaces),
                description: notes.isEmpty ? nil : notes,
                activityType: type.id,
                customer: selectedCustomerId,
                status: "planned",
                priority: priority,
                scheduledStart: Format.apiDateTime(scheduledStart),
                scheduledEnd: Format.apiDateTime(scheduledEnd),
                notes: notes.isEmpty ? nil : notes
            )
            if let error = await model.save(activity) {
                errorMessage = error
            } else {
                dismiss()
            }
        }
    }
}
