package com.microimage.crm.api

import com.microimage.crm.model.LoginRequest
import com.microimage.crm.model.LoginResponse
import com.microimage.crm.model.User
import com.microimage.crm.model.SalesFunnel
import com.microimage.crm.model.Proposal
import com.microimage.crm.model.ProposalCreatePayload
import com.microimage.crm.model.ProposalDetail
import com.microimage.crm.model.PendingApproval
import com.microimage.crm.model.ApprovalDecisionPayload
import com.microimage.crm.model.SalesActivity
import com.microimage.crm.model.SalesActivityCreatePayload
import com.microimage.crm.model.CustomerSummary
import com.microimage.crm.model.CustomerDetail
import com.microimage.crm.model.CustomerCreateRequestPayload
import com.microimage.crm.model.CustomerRequest
import com.microimage.crm.model.CampaignSummary
import com.microimage.crm.model.CampaignPreview
import com.microimage.crm.model.ApiMessage
import com.microimage.crm.model.ActivityCompletePayload
import com.microimage.crm.model.ActivityType
import com.microimage.crm.model.ActivityUpdatePayload
import com.microimage.crm.model.CustomerChoices
import com.microimage.crm.model.DashboardSummary
import com.microimage.crm.model.MfaVerifyRequest
import okhttp3.ResponseBody
import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.Header
import retrofit2.http.PATCH
import retrofit2.http.POST
import retrofit2.http.Path
import retrofit2.http.Query
import retrofit2.http.Streaming

interface ApiService {
    @POST("api-token-auth/")
    suspend fun login(@Body request: LoginRequest): Response<LoginResponse>

    /** Second leg of an MFA sign-in: trade the interim token + TOTP code for an API token. */
    @POST("api-token-auth/mfa/")
    suspend fun verifyMfa(@Body request: MfaVerifyRequest): Response<LoginResponse>

    /** Revokes the API token server-side. */
    @POST("logout/")
    suspend fun logout(@Header("Authorization") token: String): Response<ApiMessage>

    @GET("users/me/")
    suspend fun getCurrentUser(@Header("Authorization") token: String): Response<User>

    @GET("dashboard/")
    suspend fun getDashboard(@Header("Authorization") token: String): Response<DashboardSummary>

    @GET("funnel/")
    suspend fun getSalesFunnel(
        @Header("Authorization") token: String,
        @Query("stage") stage: String? = null
    ): Response<List<SalesFunnel>>

    @GET("customers/")
    suspend fun getCustomers(
        @Header("Authorization") token: String,
        @Query("search") search: String? = null,
        @Query("industry") industry: String? = null,
        @Query("territory") territory: String? = null
    ): Response<List<CustomerSummary>>

    @GET("customers/mine/")
    suspend fun getMyCustomers(
        @Header("Authorization") token: String,
        @Query("search") search: String? = null
    ): Response<List<CustomerSummary>>

    @GET("customers/choices/")
    suspend fun getCustomerChoices(@Header("Authorization") token: String): Response<CustomerChoices>

    @GET("customers/{id}/")
    suspend fun getCustomerDetail(
        @Header("Authorization") token: String,
        @Path("id") customerId: Int
    ): Response<CustomerDetail>

    @POST("customer-requests/")
    suspend fun createCustomerRequest(
        @Header("Authorization") token: String,
        @Body request: CustomerCreateRequestPayload
    ): Response<CustomerRequest>

    @GET("customer-requests/mine/")
    suspend fun getMyCustomerRequests(@Header("Authorization") token: String): Response<List<CustomerRequest>>

    @GET("customer-requests/pending/")
    suspend fun getPendingCustomerRequests(@Header("Authorization") token: String): Response<List<CustomerRequest>>

    @POST("customer-requests/{id}/approve/")
    suspend fun approveCustomerRequest(
        @Header("Authorization") token: String,
        @Path("id") requestId: Int
    ): Response<Map<String, Any>>

    @POST("customer-requests/{id}/reject/")
    suspend fun rejectCustomerRequest(
        @Header("Authorization") token: String,
        @Path("id") requestId: Int,
        @Body payload: Map<String, String>
    ): Response<Map<String, Any>>

    @GET("proposals/")
    suspend fun getProposals(
        @Header("Authorization") token: String,
        @Query("search") search: String? = null,
        @Query("approval_status") approvalStatus: String? = null
    ): Response<List<Proposal>>

    /** Streams the rendered quotation PDF. */
    @Streaming
    @GET("proposals/{id}/pdf/")
    suspend fun downloadProposalPdf(
        @Header("Authorization") token: String,
        @Path("id") proposalId: Int
    ): Response<ResponseBody>

    @GET("proposals/{id}/")
    suspend fun getProposalDetail(
        @Header("Authorization") token: String,
        @Path("id") proposalId: Int
    ): Response<ProposalDetail>

    @POST("proposals/")
    suspend fun createProposal(
        @Header("Authorization") token: String,
        @Body request: ProposalCreatePayload
    ): Response<ProposalDetail>

    @GET("proposals/pending_approvals/")
    suspend fun getPendingProposalApprovals(@Header("Authorization") token: String): Response<List<PendingApproval>>

    @POST("proposals/{id}/approve/")
    suspend fun approveProposal(
        @Header("Authorization") token: String,
        @Path("id") proposalId: Int,
        @Body request: ApprovalDecisionPayload
    ): Response<Map<String, Any>>

    @POST("proposals/{id}/reject/")
    suspend fun rejectProposal(
        @Header("Authorization") token: String,
        @Path("id") proposalId: Int,
        @Body request: ApprovalDecisionPayload
    ): Response<Map<String, Any>>

    @GET("activities/")
    suspend fun getSalesActivities(
        @Header("Authorization") token: String,
        @Query("status") status: String? = null,
        @Query("customer") customerId: Int? = null,
        @Query("upcoming") upcoming: Boolean? = null,
        @Query("mine") mine: Boolean? = null
    ): Response<List<SalesActivity>>

    @GET("activities/{id}/")
    suspend fun getSalesActivityDetail(
        @Header("Authorization") token: String,
        @Path("id") activityId: Int
    ): Response<SalesActivity>

    @POST("activities/")
    suspend fun createSalesActivity(
        @Header("Authorization") token: String,
        @Body request: SalesActivityCreatePayload
    ): Response<SalesActivity>

    @PATCH("activities/{id}/")
    suspend fun updateSalesActivity(
        @Header("Authorization") token: String,
        @Path("id") activityId: Int,
        @Body request: ActivityUpdatePayload
    ): Response<SalesActivity>

    @POST("activities/{id}/complete/")
    suspend fun completeSalesActivity(
        @Header("Authorization") token: String,
        @Path("id") activityId: Int,
        @Body request: ActivityCompletePayload
    ): Response<SalesActivity>

    /**
     * Activity types for the create form. Without this the create screen
     * hardcoded `activityType = 1`.
     */
    @GET("activity-types/")
    suspend fun getActivityTypes(@Header("Authorization") token: String): Response<List<ActivityType>>

    @GET("campaigns/")
    suspend fun getCampaigns(@Header("Authorization") token: String): Response<List<CampaignSummary>>

    @GET("campaigns/{id}/preview/")
    suspend fun previewCampaign(
        @Header("Authorization") token: String,
        @Path("id") campaignId: Int
    ): Response<CampaignPreview>

    @POST("campaigns/{id}/send/")
    suspend fun sendCampaign(
        @Header("Authorization") token: String,
        @Path("id") campaignId: Int
    ): Response<ApiMessage>

    @POST("campaigns/{id}/cancel/")
    suspend fun cancelCampaign(
        @Header("Authorization") token: String,
        @Path("id") campaignId: Int
    ): Response<ApiMessage>
}
