package com.microimage.crm.ui.proposal

import android.widget.Toast
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.navigation.NavController
import com.microimage.crm.api.RetrofitClient
import com.microimage.crm.model.ApprovalDecisionPayload
import com.microimage.crm.model.ProposalApprovalStep
import com.microimage.crm.model.ProposalDetail
import com.microimage.crm.ui.theme.Hairline
import com.microimage.crm.ui.theme.MetricRow
import com.microimage.crm.ui.theme.MiPalette
import com.microimage.crm.ui.theme.RowCard
import com.microimage.crm.ui.theme.SectionHeading
import com.microimage.crm.ui.theme.StatusColors
import com.microimage.crm.ui.theme.StatusTag
import com.microimage.crm.ui.theme.fullCurrency
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ProposalDetailScreen(token: String, proposalId: Int, navController: NavController) {
    val scope = rememberCoroutineScope()
    val context = androidx.compose.ui.platform.LocalContext.current
    var proposal by remember { mutableStateOf<ProposalDetail?>(null) }
    var isLoading by remember { mutableStateOf(true) }
    var errorMessage by remember { mutableStateOf<String?>(null) }
    var isActing by remember { mutableStateOf(false) }

    // null = no dialog; true = approve; false = reject
    var decision by remember { mutableStateOf<Boolean?>(null) }

    fun loadDetail() {
        isLoading = true
        scope.launch {
            try {
                val response = RetrofitClient.apiService.getProposalDetail("Token $token", proposalId)
                if (response.isSuccessful) {
                    proposal = response.body()
                    errorMessage = null
                } else {
                    errorMessage = "Error: ${response.code()}"
                }
            } catch (e: Exception) {
                errorMessage = e.message
            } finally {
                isLoading = false
            }
        }
    }

    LaunchedEffect(proposalId) { loadDetail() }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(proposal?.proposalNumber ?: "Proposal") },
                navigationIcon = {
                    IconButton(onClick = { navController.popBackStack() }) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = MiPalette.surface)
            )
        }
    ) { padding ->
        Box(
            modifier = Modifier
                .padding(padding)
                .fillMaxSize()
                .background(MiPalette.canvas)
        ) {
            when {
                isLoading -> CircularProgressIndicator(
                    modifier = Modifier.align(Alignment.Center),
                    color = MiPalette.brand
                )
                errorMessage != null && proposal == null -> Text(
                    errorMessage!!,
                    modifier = Modifier.align(Alignment.Center),
                    color = MiPalette.inkMuted
                )
                proposal != null -> ProposalDetailContent(
                    proposal = proposal!!,
                    isActing = isActing,
                    onApprove = { decision = true },
                    onReject = { decision = false },
                    onOpenCustomer = { /* optional: navigate to customer detail */ }
                )
            }
        }
    }

    // Approve / Reject confirmation with an optional comment / required reason.
    if (decision != null) {
        val approve = decision == true
        DecisionDialog(
            approve = approve,
            isActing = isActing,
            onDismiss = { if (!isActing) decision = null },
            onSubmit = { comment ->
                isActing = true
                scope.launch {
                    try {
                        val payload = ApprovalDecisionPayload(comment.ifBlank { if (approve) "Approved from App" else "Rejected from App" })
                        val res = if (approve)
                            RetrofitClient.apiService.approveProposal("Token $token", proposalId, payload)
                        else
                            RetrofitClient.apiService.rejectProposal("Token $token", proposalId, payload)
                        if (res.isSuccessful) {
                            Toast.makeText(context, if (approve) "Approved" else "Rejected", Toast.LENGTH_SHORT).show()
                            decision = null
                            loadDetail()
                        } else {
                            Toast.makeText(context, "Failed: ${res.code()}", Toast.LENGTH_SHORT).show()
                        }
                    } catch (e: Exception) {
                        Toast.makeText(context, e.message ?: "Error", Toast.LENGTH_SHORT).show()
                    } finally {
                        isActing = false
                    }
                }
            }
        )
    }
}

@Composable
private fun ProposalDetailContent(
    proposal: ProposalDetail,
    isActing: Boolean,
    onApprove: () -> Unit,
    onReject: () -> Unit,
    onOpenCustomer: () -> Unit
) {
    val symbol = if (proposal.currency.uppercase() == "USD") "$" else "₱"

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 20.dp, vertical = 16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        // Header card: subject, big amount, status tags.
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(14.dp))
                .background(MiPalette.surface)
                .padding(20.dp)
        ) {
            Text(
                text = proposal.subject,
                fontSize = 23.sp,
                fontWeight = FontWeight.Bold,
                color = MiPalette.ink
            )
            Text(
                text = fullCurrency(proposal.totalAmount, symbol),
                fontSize = 32.sp,
                fontWeight = FontWeight.Bold,
                color = MiPalette.ink,
                modifier = Modifier.padding(top = 8.dp)
            )
            Row(
                modifier = Modifier.padding(top = 10.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                StatusTag(
                    text = StatusColors.label(proposal.approvalStatus),
                    color = StatusColors.color(proposal.approvalStatus)
                )
                if (proposal.statusDisplay.isNotBlank()) {
                    StatusTag(text = proposal.statusDisplay, color = MiPalette.inkMuted)
                }
            }
        }

        // Approve / Reject
        if (proposal.canCurrentUserApprove) {
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Button(
                    onClick = onApprove,
                    enabled = !isActing,
                    modifier = Modifier.weight(1f).height(50.dp),
                    shape = RoundedCornerShape(10.dp),
                    colors = ButtonDefaults.buttonColors(containerColor = MiPalette.brand)
                ) { Text("Approve", fontWeight = FontWeight.SemiBold) }
                OutlinedButton(
                    onClick = onReject,
                    enabled = !isActing,
                    modifier = Modifier.weight(1f).height(50.dp),
                    shape = RoundedCornerShape(10.dp)
                ) { Text("Reject", color = MiPalette.ink) }
            }
        }

        // Approval chain
        if (proposal.approvalSteps.isNotEmpty()) {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                SectionHeading(title = "Approval chain")
                RowCard {
                    proposal.approvalSteps.forEachIndexed { index, step ->
                        if (index > 0) Hairline()
                        ApprovalStepRow(step)
                    }
                }
            }
        }

        // Figures
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            SectionHeading(title = "Figures")
            RowCard {
                MetricRow("Subtotal", fullCurrency(proposal.subtotal, symbol))
                Hairline()
                MetricRow("Tax", fullCurrency(proposal.taxAmount, symbol))
                Hairline()
                MetricRow("Total", fullCurrency(proposal.totalAmount, symbol))
                if (!proposal.referenceNumber.isNullOrBlank()) {
                    Hairline()
                    MetricRow("Reference", proposal.referenceNumber!!)
                }
            }
        }

        // Customer
        proposal.customer?.let { c ->
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                SectionHeading(title = "Customer")
                RowCard {
                    Column(modifier = Modifier.padding(vertical = 12.dp)) {
                        Text(c.companyName, fontSize = 16.sp, fontWeight = FontWeight.Medium, color = MiPalette.ink)
                        if (c.contactPersonName.isNotBlank()) {
                            Text(c.contactPersonName, fontSize = 13.sp, color = MiPalette.inkMuted, modifier = Modifier.padding(top = 3.dp))
                        }
                    }
                }
            }
        }

        Spacer(modifier = Modifier.height(8.dp))
    }
}

@Composable
private fun ApprovalStepRow(step: ProposalApprovalStep) {
    val color = StatusColors.color(step.status)
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Box(
            modifier = Modifier
                .size(24.dp)
                .clip(RoundedCornerShape(50))
                .background(color.copy(alpha = 0.12f)),
            contentAlignment = Alignment.Center
        ) {
            Text("${step.level}", fontSize = 12.sp, fontWeight = FontWeight.SemiBold, color = color)
        }
        Spacer(modifier = Modifier.width(12.dp))
        Column(modifier = Modifier.weight(1f)) {
            Text(step.approverName ?: "Unassigned", fontSize = 16.sp, fontWeight = FontWeight.Medium, color = MiPalette.ink)
            if (!step.comment.isNullOrBlank()) {
                Text(step.comment!!, fontSize = 13.sp, color = MiPalette.inkMuted, modifier = Modifier.padding(top = 3.dp))
            }
        }
        Spacer(modifier = Modifier.width(8.dp))
        val label = if (step.isCurrent && step.status.lowercase() == "pending") "With them now" else StatusColors.label(step.status)
        StatusTag(text = label, color = color)
    }
}

@Composable
private fun DecisionDialog(
    approve: Boolean,
    isActing: Boolean,
    onDismiss: () -> Unit,
    onSubmit: (String) -> Unit
) {
    var comment by remember { mutableStateOf("") }
    val canSubmit = approve || comment.trim().isNotEmpty()

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(if (approve) "Approve proposal" else "Reject proposal") },
        text = {
            Column {
                Text(
                    if (approve)
                        "This moves the proposal to the next approver, or marks it fully approved if you're the last."
                    else
                        "Rejecting ends the approval chain. The salesperson is notified with your reason.",
                    fontSize = 14.sp,
                    color = MiPalette.inkMuted
                )
                Spacer(modifier = Modifier.height(12.dp))
                OutlinedTextField(
                    value = comment,
                    onValueChange = { comment = it },
                    label = { Text(if (approve) "Comment (optional)" else "Reason") },
                    modifier = Modifier.fillMaxWidth(),
                    minLines = 3
                )
            }
        },
        confirmButton = {
            TextButton(
                onClick = { onSubmit(comment) },
                enabled = canSubmit && !isActing
            ) {
                if (isActing) {
                    CircularProgressIndicator(modifier = Modifier.size(18.dp), color = MiPalette.brand, strokeWidth = 2.dp)
                } else {
                    Text(if (approve) "Approve" else "Reject", color = if (approve) MiPalette.brand else MiPalette.critical, fontWeight = FontWeight.SemiBold)
                }
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss, enabled = !isActing) { Text("Cancel") }
        }
    )
}
