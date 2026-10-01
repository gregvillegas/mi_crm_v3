import SwiftUI

struct MoreView: View {
    @Environment(Session.self) private var session
    @State private var showingSignOutConfirm = false

    var body: some View {
        ScreenScroll {
            profile

            VStack(alignment: .leading, spacing: 10) {
                SectionHeading(title: "Elsewhere in the CRM")
                RowCard {
                    NavigationLink { FunnelView() } label: {
                        NavRow(title: "Sales funnel", subtitle: "Deals by stage", systemImage: "chart.bar")
                    }
                    .buttonStyle(.plain)
                    Hairline()
                    NavigationLink { MyCustomerRequestsView() } label: {
                        NavRow(title: "My requests", subtitle: "Customers awaiting approval", systemImage: "paperplane")
                    }
                    .buttonStyle(.plain)
                    if session.canReviewApprovals {
                        Hairline()
                        NavigationLink { PendingCustomerRequestsView() } label: {
                            NavRow(title: "Requests to review", subtitle: "From your team", systemImage: "person.badge.plus")
                        }
                        .buttonStyle(.plain)
                    }
                    Hairline()
                    NavigationLink { ApprovalInboxView() } label: {
                        NavRow(title: "Approvals", subtitle: "Proposals waiting on you", systemImage: "checkmark.seal")
                    }
                    .buttonStyle(.plain)
                    Hairline()
                    NavigationLink { CampaignListView() } label: {
                        NavRow(title: "Campaigns", subtitle: "Email delivery progress", systemImage: "envelope")
                    }
                    .buttonStyle(.plain)
                }
            }

            VStack(alignment: .leading, spacing: 10) {
                SectionHeading(title: "Connection")
                RowCard {
                    MetricRow(label: "Server", value: session.serverHost)
                }
            }

            Button("Sign out") { showingSignOutConfirm = true }
                .buttonStyle(SecondaryButtonStyle())

            Text("MiCRM for iOS · Version 1.0")
                .font(TypeScale.caption)
                .foregroundStyle(Palette.inkFaint)
                .frame(maxWidth: .infinity, alignment: .center)
        }
        .background(Palette.canvas)
        .navigationTitle("More")
        .confirmationDialog(
            "Sign out of MiCRM?",
            isPresented: $showingSignOutConfirm,
            titleVisibility: .visible
        ) {
            Button("Sign out", role: .destructive) {
                Task { await session.signOut() }
            }
            Button("Stay signed in", role: .cancel) {}
        } message: {
            Text("This revokes this device's access token. You'll need your password, and your authenticator code, to sign back in.")
        }
    }

    private var profile: some View {
        HStack(spacing: 14) {
            Text(session.user.map { Format.initials(from: $0.displayName) } ?? "?")
                .font(.system(size: 17, weight: .semibold))
                .foregroundStyle(.white)
                .frame(width: 52, height: 52)
                .background(Palette.brand, in: RoundedRectangle(cornerRadius: 13))

            VStack(alignment: .leading, spacing: 3) {
                Text(session.user?.displayName ?? "Signed in")
                    .font(TypeScale.sectionTitle)
                    .foregroundStyle(Palette.ink)
                Text(session.user?.email ?? "")
                    .font(TypeScale.caption)
                    .foregroundStyle(Palette.inkMuted)
            }

            Spacer()
        }
        .padding(Metrics.gutter)
        .background(Palette.surface, in: RoundedRectangle(cornerRadius: Metrics.cardRadius))
    }
}

struct NavRow: View {
    let title: String
    let subtitle: String
    let systemImage: String

    var body: some View {
        HStack(spacing: 13) {
            Image(systemName: systemImage)
                .font(.system(size: 15))
                .foregroundStyle(Palette.inkMuted)
                .frame(width: 26)

            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(TypeScale.rowTitle)
                    .foregroundStyle(Palette.ink)
                Text(subtitle)
                    .font(TypeScale.caption)
                    .foregroundStyle(Palette.inkMuted)
            }

            Spacer(minLength: 8)

            Image(systemName: "chevron.right")
                .font(.system(size: 12, weight: .semibold))
                .foregroundStyle(Palette.inkFaint)
        }
        .padding(.vertical, 12)
        .contentShape(Rectangle())
    }
}
