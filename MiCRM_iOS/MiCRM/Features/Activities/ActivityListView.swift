import SwiftUI

@MainActor
@Observable
final class ActivityListModel {
    enum Filter: String, CaseIterable, Identifiable {
        case upcoming, overdue, completed
        var id: String { rawValue }

        var label: String {
            switch self {
            case .upcoming: return "Upcoming"
            case .overdue: return "Overdue"
            case .completed: return "Done"
            }
        }
    }

    var activities: [SalesActivity] = []
    var isLoading = true
    var errorMessage: String?
    var filter: Filter = .upcoming
    var completingId: Int?

    func load() async {
        errorMessage = nil
        do {
            let all: [SalesActivity]
            switch filter {
            case .upcoming:
                all = try await APIClient.shared.activities(upcomingOnly: true)
            case .completed:
                all = try await APIClient.shared.activities(status: "completed")
            case .overdue:
                // The API has no overdue filter; it is a client-side reading of
                // scheduled_end against now, same as the dashboard counter.
                all = try await APIClient.shared.activities().filter(\.isOverdue)
            }
            activities = all
        } catch {
            errorMessage = (error as? APIError)?.errorDescription ?? error.localizedDescription
        }
        isLoading = false
    }

    func complete(_ activity: SalesActivity) async {
        completingId = activity.id
        defer { completingId = nil }
        do {
            _ = try await APIClient.shared.completeActivity(id: activity.id, notes: nil)
            await load()
        } catch {
            errorMessage = (error as? APIError)?.errorDescription ?? error.localizedDescription
        }
    }
}

struct ActivityListView: View {
    var initialFilter: ActivityListModel.Filter = .upcoming

    @State private var model = ActivityListModel()
    @State private var showingCreate = false
    @State private var didApplyInitialFilter = false

    var body: some View {
        Group {
            if model.isLoading {
                LoadingState()
            } else if let message = model.errorMessage, model.activities.isEmpty {
                ErrorState(message: message) { Task { await model.load() } }
            } else {
                list
            }
        }
        .background(Palette.canvas)
        .navigationTitle("Schedule")
        .toolbar {
            ToolbarItem {
                Button { showingCreate = true } label: { Image(systemName: "plus") }
                    .accessibilityLabel("Log an activity")
            }
        }
        .sheet(isPresented: $showingCreate, onDismiss: { Task { await model.load() } }) {
            NavigationStack { ActivityCreateView() }
        }
        .task {
            if !didApplyInitialFilter {
                model.filter = initialFilter
                didApplyInitialFilter = true
            }
            await model.load()
        }
        .refreshable { await model.load() }
    }

    private var list: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                Picker("Filter", selection: Binding(
                    get: { model.filter },
                    set: { model.filter = $0; Task { await model.load() } }
                )) {
                    ForEach(ActivityListModel.Filter.allCases) { filter in
                        Text(filter.label).tag(filter)
                    }
                }
                .pickerStyle(.segmented)

                if model.activities.isEmpty {
                    EmptyState(
                        title: emptyTitle,
                        message: emptyMessage,
                        systemImage: "calendar",
                        action: model.filter == .upcoming
                            ? (title: "Log an activity", handler: { showingCreate = true })
                            : nil
                    )
                    .frame(minHeight: 260)
                } else {
                    RowCard {
                        ForEach(Array(model.activities.enumerated()), id: \.element.id) { index, activity in
                            if index > 0 { Hairline() }
                            ActivityRow(
                                activity: activity,
                                isCompleting: model.completingId == activity.id,
                                onComplete: { Task { await model.complete(activity) } }
                            )
                        }
                    }
                }
            }
            .padding(.horizontal, Metrics.gutter)
            .padding(.vertical, 16)
        }
        .background(Palette.canvas)
    }

    private var emptyTitle: String {
        switch model.filter {
        case .upcoming: return "Nothing scheduled"
        case .overdue: return "Nothing overdue"
        case .completed: return "Nothing completed yet"
        }
    }

    private var emptyMessage: String {
        switch model.filter {
        case .upcoming: return "Calls, meetings and follow-ups you schedule will appear here."
        case .overdue: return "You're on top of your schedule."
        case .completed: return "Activities you mark done will be listed here."
        }
    }
}

struct ActivityRow: View {
    let activity: SalesActivity
    let isCompleting: Bool
    let onComplete: () -> Void

    private var isDone: Bool { activity.status == "completed" }

    var body: some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text(activity.title)
                    .font(TypeScale.rowTitle)
                    .foregroundStyle(Palette.ink)
                    .lineLimit(1)

                Text(
                    [activity.activityTypeDetails?.name, activity.customerName,
                     Format.schedule(activity.scheduledStart)]
                        .compactMap { $0 }
                        .joined(separator: " · ")
                )
                .font(TypeScale.caption)
                .foregroundStyle(activity.isOverdue ? Palette.critical : Palette.inkMuted)
                .lineLimit(1)
            }

            Spacer(minLength: 8)

            if isDone {
                Image(systemName: "checkmark.circle.fill")
                    .font(.system(size: 20))
                    .foregroundStyle(Palette.positive)
            } else {
                Button(action: onComplete) {
                    if isCompleting {
                        ProgressView()
                    } else {
                        Image(systemName: "circle")
                            .font(.system(size: 20, weight: .light))
                            .foregroundStyle(Palette.inkFaint)
                    }
                }
                .buttonStyle(.plain)
                .disabled(isCompleting)
                .accessibilityLabel("Mark \(activity.title) done")
            }
        }
        .padding(.vertical, 12)
    }
}
