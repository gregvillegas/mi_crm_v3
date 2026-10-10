package com.microimage.crm.ui

sealed class Screen(val route: String) {
    object Unlock : Screen("unlock")
    object Login : Screen("login")
    object Dashboard : Screen("dashboard/{token}") {
        fun createRoute(token: String) = "dashboard/$token"
    }
    
    // Customers
    object CustomerList : Screen("customers/{token}") {
        fun createRoute(token: String) = "customers/$token"
    }
    object CustomerDetail : Screen("customer_detail/{token}/{id}") {
        fun createRoute(token: String, id: Int) = "customer_detail/$token/$id"
    }
    object CustomerCreateRequest : Screen("customer_create_request/{token}") {
        fun createRoute(token: String) = "customer_create_request/$token"
    }
    object MyCustomerRequests : Screen("my_customer_requests/{token}") {
        fun createRoute(token: String) = "my_customer_requests/$token"
    }
    object PendingCustomerRequests : Screen("pending_customer_requests/{token}") {
        fun createRoute(token: String) = "pending_customer_requests/$token"
    }

    // Proposals
    object SalesProposal : Screen("sales_proposal/{token}") {
        fun createRoute(token: String) = "sales_proposal/$token"
    }
    object ProposalDetail : Screen("proposal_detail/{token}/{id}") {
        fun createRoute(token: String, id: Int) = "proposal_detail/$token/$id"
    }
    object ProposalCreate : Screen("proposal_create/{token}") {
        fun createRoute(token: String) = "proposal_create/$token"
    }
    object PendingProposalApprovals : Screen("pending_proposal_approvals/{token}") {
        fun createRoute(token: String) = "pending_proposal_approvals/$token"
    }

    // Sales Monitoring
    object SalesFunnel : Screen("sales_funnel/{token}") {
        fun createRoute(token: String) = "sales_funnel/$token"
    }
    object FunnelDetail : Screen("funnel_detail/{token}/{id}") {
        fun createRoute(token: String, id: Int) = "funnel_detail/$token/$id"
    }
    object SalesActivityCreate : Screen("sales_activity_create/{token}") {
        fun createRoute(token: String) = "sales_activity_create/$token"
    }
    object SalesActivityDetail : Screen("sales_activity_detail/{token}/{id}") {
        fun createRoute(token: String, id: Int) = "sales_activity_detail/$token/$id"
    }

    // Campaigns
    object CampaignList : Screen("campaigns/{token}") {
        fun createRoute(token: String) = "campaigns/$token"
    }

    object Settings : Screen("settings/{token}") {
        fun createRoute(token: String) = "settings/$token"
    }

    // Global search (proposals + customers + funnel)
    object GlobalSearch : Screen("global_search/{token}") {
        fun createRoute(token: String) = "global_search/$token"
    }
}
