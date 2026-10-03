package com.microimage.crm.model

import com.google.gson.annotations.SerializedName

data class User(
    @SerializedName("id") val id: Int,
    @SerializedName("username") val username: String,
    @SerializedName("email") val email: String,
    @SerializedName("first_name") val firstName: String,
    @SerializedName("last_name") val lastName: String,
    @SerializedName("role") val role: String
)

/**
 * Response to POST api-token-auth/.
 *
 * Two shapes share this type: a completed sign-in carries [token], while an
 * account with MFA enrolled carries [mfaRequired] + [mfaToken] and no token —
 * the caller must then post the authenticator code to api-token-auth/mfa/.
 */
data class LoginResponse(
    @SerializedName("token") val token: String? = null,
    @SerializedName("user_id") val userId: Int? = null,
    @SerializedName("username") val username: String? = null,
    @SerializedName("email") val email: String? = null,
    @SerializedName("first_name") val firstName: String? = null,
    @SerializedName("last_name") val lastName: String? = null,
    @SerializedName("role") val role: String? = null,
    @SerializedName("role_display") val roleDisplay: String? = null,
    @SerializedName("mfa_required") val mfaRequired: Boolean = false,
    @SerializedName("mfa_token") val mfaToken: String? = null,
    @SerializedName("mfa_setup_required") val mfaSetupRequired: Boolean = false,
    @SerializedName("setup_url") val setupUrl: String? = null,
    @SerializedName("detail") val detail: String? = null
)

data class LoginRequest(
    @SerializedName("username") val username: String,
    @SerializedName("password") val password: String
)

data class MfaVerifyRequest(
    @SerializedName("mfa_token") val mfaToken: String,
    @SerializedName("code") val code: String
)

data class SalesFunnel(
    @SerializedName("id") val id: Int,
    @SerializedName("company_name") val companyName: String,
    @SerializedName("stage_display") val stage: String,
    @SerializedName("retail") val retail: Double,
    @SerializedName("probability") val probability: Int
)

data class CustomerContact(
    @SerializedName("id") val id: Int? = null,
    @SerializedName("name") val name: String,
    @SerializedName("position") val position: String? = null,
    @SerializedName("email") val email: String? = null,
    @SerializedName("phone") val phone: String? = null,
    @SerializedName("is_primary") val isPrimary: Boolean = false
)

data class CustomerSummary(
    @SerializedName("id") val id: Int,
    @SerializedName("company_name") val companyName: String,
    @SerializedName("contact_person_name") val contactPersonName: String,
    @SerializedName("contact_person_position") val contactPersonPosition: String? = null,
    @SerializedName("email") val email: String,
    @SerializedName("phone_number") val phoneNumber: String? = null,
    @SerializedName("industry") val industry: String? = null,
    @SerializedName("territory") val territory: String? = null,
    @SerializedName("display_status") val displayStatus: String? = null,
    @SerializedName("is_active") val isActive: Boolean,
    @SerializedName("auto_inactive_flag") val autoInactiveFlag: Boolean,
    @SerializedName("is_millionaire_account") val isMillionaireAccount: Boolean,
    @SerializedName("salesperson_name") val salespersonName: String? = null,
    @SerializedName("salesperson_initials") val salespersonInitials: String? = null
)

data class CustomerDetail(
    @SerializedName("id") val id: Int,
    @SerializedName("company_name") val companyName: String,
    @SerializedName("contact_person_name") val contactPersonName: String,
    @SerializedName("contact_person_position") val contactPersonPosition: String? = null,
    @SerializedName("email") val email: String,
    @SerializedName("phone_number") val phoneNumber: String? = null,
    @SerializedName("address") val address: String? = null,
    @SerializedName("industry") val industry: String? = null,
    @SerializedName("territory") val territory: String? = null,
    @SerializedName("display_status") val displayStatus: String? = null,
    @SerializedName("is_active") val isActive: Boolean,
    @SerializedName("auto_inactive_flag") val autoInactiveFlag: Boolean,
    @SerializedName("is_millionaire_account") val isMillionaireAccount: Boolean,
    @SerializedName("salesperson") val salespersonId: Int? = null,
    @SerializedName("salesperson_name") val salespersonName: String? = null,
    @SerializedName("contacts") val contacts: List<CustomerContact> = emptyList()
)

data class CustomerCreateRequestPayload(
    @SerializedName("company_name") val companyName: String,
    @SerializedName("contact_person_name") val contactPersonName: String,
    @SerializedName("contact_person_position") val contactPersonPosition: String? = null,
    @SerializedName("email") val email: String,
    @SerializedName("phone_number") val phoneNumber: String? = null,
    @SerializedName("address") val address: String? = null,
    @SerializedName("industry") val industry: String? = null,
    @SerializedName("territory") val territory: String? = null
)

data class CustomerRequest(
    @SerializedName("id") val id: Int,
    @SerializedName("company_name") val companyName: String,
    @SerializedName("contact_person_name") val contactPersonName: String,
    @SerializedName("email") val email: String,
    @SerializedName("status") val status: String,
    @SerializedName("decision_notes") val decisionNotes: String? = null,
    @SerializedName("similar_matches") val similarMatches: List<Map<String, Any?>>? = null,
    @SerializedName("created_at") val createdAt: String,
    @SerializedName("reviewed_at") val reviewedAt: String? = null
)

data class Proposal(
    @SerializedName("id") val id: Int,
    @SerializedName("proposal_number") val proposalNumber: String,
    @SerializedName("subject") val subject: String,
    @SerializedName("customer_name") val customerName: String,
    @SerializedName("total_amount") val totalAmount: Double,
    @SerializedName("status_display") val status: String,
    @SerializedName("currency") val currency: String
)

data class ProposalItemPayload(
    @SerializedName("part_number") val partNumber: String? = null,
    @SerializedName("description") val description: String,
    @SerializedName("quantity") val quantity: Double,
    @SerializedName("unit_cost") val unitCost: Double = 0.0,
    @SerializedName("unit_price") val unitPrice: Double,
    @SerializedName("availability") val availability: String? = null,
    @SerializedName("warranty") val warranty: String? = null
)

data class ProposalCreatePayload(
    @SerializedName("customer") val customer: Int,
    @SerializedName("contact_name") val contactName: String? = null,
    @SerializedName("contact_email") val contactEmail: String? = null,
    @SerializedName("contact_phone") val contactPhone: String? = null,
    @SerializedName("subject") val subject: String,
    @SerializedName("currency") val currency: String = "PHP",
    @SerializedName("exchange_rate") val exchangeRate: Double = 1.0,
    @SerializedName("date") val date: String? = null,
    @SerializedName("valid_until") val validUntil: String? = null,
    @SerializedName("price_validity_mode") val priceValidityMode: String = "date_only",
    @SerializedName("payment_terms") val paymentTerms: String? = null,
    @SerializedName("delivery_lead_time") val deliveryLeadTime: String? = null,
    @SerializedName("cancellation_terms") val cancellationTerms: String? = null,
    @SerializedName("include_bank_details") val includeBankDetails: Boolean = false,
    @SerializedName("introduction") val introduction: String? = null,
    @SerializedName("special_note") val specialNote: String? = null,
    @SerializedName("closing") val closing: String? = null,
    @SerializedName("tax_type") val taxType: String = "VAT",
    @SerializedName("tax_rate") val taxRate: Double = 12.0,
    @SerializedName("sales_margin_pct") val salesMarginPct: Double = 0.0,
    @SerializedName("items") val items: List<ProposalItemPayload>
)

data class ProposalApprovalStep(
    @SerializedName("id") val id: Int,
    @SerializedName("level") val level: Int,
    @SerializedName("approver_name") val approverName: String? = null,
    @SerializedName("status") val status: String,
    @SerializedName("comment") val comment: String? = null,
    @SerializedName("is_current") val isCurrent: Boolean = false
)

data class ProposalDetail(
    @SerializedName("id") val id: Int,
    @SerializedName("proposal_number") val proposalNumber: String,
    @SerializedName("reference_number") val referenceNumber: String? = null,
    @SerializedName("subject") val subject: String,
    @SerializedName("status") val status: String,
    @SerializedName("status_display") val statusDisplay: String,
    @SerializedName("approval_status") val approvalStatus: String,
    @SerializedName("approval_required") val approvalRequired: Boolean,
    @SerializedName("can_current_user_approve") val canCurrentUserApprove: Boolean,
    @SerializedName("total_amount") val totalAmount: Double,
    @SerializedName("subtotal") val subtotal: Double,
    @SerializedName("tax_amount") val taxAmount: Double,
    @SerializedName("total_cost") val totalCost: Double,
    @SerializedName("gross_profit") val grossProfit: Double,
    @SerializedName("currency") val currency: String,
    @SerializedName("customer") val customer: CustomerSummary? = null,
    @SerializedName("items") val items: List<ProposalItemPayload> = emptyList(),
    @SerializedName("approval_steps") val approvalSteps: List<ProposalApprovalStep> = emptyList()
)

data class ApprovalDecisionPayload(
    @SerializedName("comment") val comment: String? = null
)

data class PendingApproval(
    @SerializedName("id") val id: Int,
    @SerializedName("proposal_id") val proposalId: Int,
    @SerializedName("proposal_number") val proposalNumber: String,
    @SerializedName("customer_name") val customerName: String,
    @SerializedName("subject") val subject: String,
    @SerializedName("total_amount") val totalAmount: Double,
    @SerializedName("currency") val currency: String,
    @SerializedName("level") val level: Int
)

data class ActivityType(
    @SerializedName("id") val id: Int? = null,
    @SerializedName("name") val name: String,
    @SerializedName("icon") val icon: String,
    @SerializedName("color") val color: String
)

data class SalesActivity(
    @SerializedName("id") val id: Int,
    @SerializedName("title") val title: String,
    @SerializedName("activity_type_details") val activityType: ActivityType?,
    @SerializedName("status_display") val status: String,
    @SerializedName("scheduled_start") val scheduledStart: String?,
    @SerializedName("customer_name") val customerName: String?
)

data class SalesActivityCreatePayload(
    @SerializedName("title") val title: String,
    @SerializedName("description") val description: String? = null,
    @SerializedName("activity_type") val activityType: Int,
    @SerializedName("customer") val customer: Int? = null,
    @SerializedName("salesperson") val salesperson: Int? = null,
    @SerializedName("status") val status: String = "planned",
    @SerializedName("priority") val priority: String = "medium",
    @SerializedName("scheduled_start") val scheduledStart: String? = null,
    @SerializedName("scheduled_end") val scheduledEnd: String? = null,
    @SerializedName("notes") val notes: String? = null,
    @SerializedName("follow_up_required") val followUpRequired: Boolean = false,
    @SerializedName("follow_up_date") val followUpDate: String? = null
)

data class CampaignSummary(
    @SerializedName("id") val id: Int,
    @SerializedName("name") val name: String,
    @SerializedName("subject") val subject: String,
    @SerializedName("status") val status: String,
    @SerializedName("recipient_mode") val recipientMode: String,
    @SerializedName("template_type") val templateType: String,
    @SerializedName("total_recipients") val totalRecipients: Int,
    @SerializedName("sent_count") val sentCount: Int,
    @SerializedName("failed_count") val failedCount: Int,
    @SerializedName("scheduled_for") val scheduledFor: String? = null
)

data class CampaignPreview(
    @SerializedName("campaign_id") val campaignId: Int,
    @SerializedName("subject") val subject: String,
    @SerializedName("rendered_body") val renderedBody: String
)

data class ApiMessage(
    @SerializedName("detail") val detail: String
)

// ---------------------------------------------------------------------------
// Dashboard
//
// The home screen used to download the full funnel, proposal and activity lists
// and reduce them on-device. GET dashboard/ returns these pre-aggregated and
// already scoped to the signed-in user's role.
// ---------------------------------------------------------------------------

data class DashboardUser(
    @SerializedName("id") val id: Int,
    @SerializedName("name") val name: String,
    @SerializedName("role") val role: String,
    @SerializedName("role_display") val roleDisplay: String,
    @SerializedName("initials") val initials: String
)

data class CustomerStats(
    @SerializedName("total") val total: Int = 0,
    @SerializedName("active") val active: Int = 0,
    @SerializedName("vip") val vip: Int = 0,
    @SerializedName("needs_attention") val needsAttention: Int = 0
)

data class FunnelStage(
    @SerializedName("stage") val stage: String,
    @SerializedName("label") val label: String,
    @SerializedName("count") val count: Int = 0,
    @SerializedName("value") val value: Double = 0.0
)

data class FunnelStats(
    @SerializedName("stages") val stages: List<FunnelStage> = emptyList(),
    @SerializedName("total_value") val totalValue: Double = 0.0,
    @SerializedName("total_count") val totalCount: Int = 0
)

data class ProposalStats(
    @SerializedName("total") val total: Int = 0,
    @SerializedName("this_month") val thisMonth: Int = 0,
    @SerializedName("awaiting_approval") val awaitingApproval: Int = 0,
    @SerializedName("approved") val approved: Int = 0,
    @SerializedName("my_pending_approvals") val myPendingApprovals: Int = 0
)

data class ActivityStats(
    @SerializedName("total") val total: Int = 0,
    @SerializedName("this_month") val thisMonth: Int = 0,
    @SerializedName("completed_this_month") val completedThisMonth: Int = 0,
    @SerializedName("upcoming") val upcoming: Int = 0,
    @SerializedName("overdue") val overdue: Int = 0
)

data class CustomerRequestStats(
    @SerializedName("mine_pending") val minePending: Int = 0,
    @SerializedName("awaiting_my_review") val awaitingMyReview: Int = 0
)

data class DashboardSummary(
    @SerializedName("quote") val quote: String? = null,
    @SerializedName("user") val user: DashboardUser,
    @SerializedName("customers") val customers: CustomerStats,
    @SerializedName("funnel") val funnel: FunnelStats,
    @SerializedName("proposals") val proposals: ProposalStats,
    @SerializedName("activities") val activities: ActivityStats,
    @SerializedName("customer_requests") val customerRequests: CustomerRequestStats,
    @SerializedName("upcoming_activities") val upcomingActivities: List<SalesActivity> = emptyList(),
    @SerializedName("recent_proposals") val recentProposals: List<Proposal> = emptyList()
)

data class ChoiceOption(
    @SerializedName("value") val value: String,
    @SerializedName("label") val label: String
)

data class CustomerChoices(
    @SerializedName("industries") val industries: List<ChoiceOption> = emptyList(),
    @SerializedName("territories") val territories: List<ChoiceOption> = emptyList()
)

data class ActivityCompletePayload(
    @SerializedName("notes") val notes: String? = null
)

data class ActivityUpdatePayload(
    @SerializedName("title") val title: String? = null,
    @SerializedName("description") val description: String? = null,
    @SerializedName("status") val status: String? = null,
    @SerializedName("priority") val priority: String? = null,
    @SerializedName("scheduled_start") val scheduledStart: String? = null,
    @SerializedName("scheduled_end") val scheduledEnd: String? = null,
    @SerializedName("notes") val notes: String? = null
)
