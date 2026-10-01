import SwiftUI

@main
struct MiCRMApp: App {
    @State private var session = Session()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(session)
                .task { await session.restore() }
                .tint(Palette.brand)
        }
    }
}

struct RootView: View {
    @Environment(Session.self) private var session

    var body: some View {
        switch session.phase {
        case .loading:
            ZStack {
                Palette.canvas.ignoresSafeArea()
                ProgressView().tint(Palette.brand)
            }
        case .signedOut:
            SignInView()
        case .awaitingCode(_, let username):
            VerifyCodeView(username: username)
        case .signedIn:
            MainTabs()
        }
    }
}

struct MainTabs: View {
    @Environment(Session.self) private var session

    var body: some View {
        TabView {
            NavigationStack { DashboardView() }
                .tabItem { Label("Home", systemImage: "chart.bar.doc.horizontal") }

            NavigationStack { CustomerListView() }
                .tabItem { Label("Customers", systemImage: "building.2") }

            NavigationStack { ProposalListView() }
                .tabItem { Label("Proposals", systemImage: "doc.text") }

            NavigationStack { ActivityListView() }
                .tabItem { Label("Schedule", systemImage: "calendar") }

            NavigationStack { MoreView() }
                .tabItem { Label("More", systemImage: "ellipsis.circle") }
        }
    }
}
