package com.microimage.crm.ui.proposal

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.navigation.NavController
import com.microimage.crm.api.RetrofitClient
import com.microimage.crm.model.PendingApproval
import com.microimage.crm.ui.Screen
import com.microimage.crm.ui.theme.Hairline
import com.microimage.crm.ui.theme.MiPalette
import com.microimage.crm.ui.theme.RowCard
import com.microimage.crm.ui.theme.StatusTag
import com.microimage.crm.ui.theme.compactCurrency
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PendingProposalApprovalsScreen(token: String, navController: NavController) {
    val scope = rememberCoroutineScope()
    var approvals by remember { mutableStateOf<List<PendingApproval>>(emptyList()) }
    var isLoading by remember { mutableStateOf(true) }
    var errorMessage by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(Unit) {
        scope.launch {
            try {
                val response = RetrofitClient.apiService.getPendingProposalApprovals("Token $token")
                if (response.isSuccessful) {
                    approvals = response.body() ?: emptyList()
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

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Approvals") },
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
                errorMessage != null -> Text(
                    errorMessage!!,
                    modifier = Modifier.align(Alignment.Center),
                    color = MiPalette.inkMuted
                )
                approvals.isEmpty() -> Text(
                    "Nothing waiting on you.",
                    modifier = Modifier.align(Alignment.Center),
                    color = MiPalette.inkMuted
                )
                else -> ApprovalList(approvals) { a ->
                    navController.navigate(Screen.ProposalDetail.createRoute(token, a.proposalId))
                }
            }
        }
    }
}

@Composable
private fun ApprovalList(approvals: List<PendingApproval>, onClick: (PendingApproval) -> Unit) {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(horizontal = 20.dp, vertical = 16.dp)
    ) {
        item {
            Text(
                text = if (approvals.size == 1)
                    "1 proposal is waiting on you."
                else
                    "${approvals.size} proposals are waiting on you.",
                fontSize = 15.sp,
                color = MiPalette.inkMuted,
                modifier = Modifier.padding(bottom = 12.dp)
            )
        }
        item {
            RowCard {
                approvals.forEachIndexed { index, a ->
                    if (index > 0) Hairline()
                    ApprovalRow(a) { onClick(a) }
                }
            }
        }
    }
}

@Composable
private fun ApprovalRow(a: PendingApproval, onClick: () -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clickable { onClick() }
            .padding(vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Column(modifier = Modifier.weight(1f)) {
            Text(
                text = a.subject,
                fontSize = 16.sp,
                fontWeight = FontWeight.Medium,
                color = MiPalette.ink,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis
            )
            Text(
                text = listOf(a.proposalNumber, a.customerName).filter { it.isNotBlank() }.joinToString(" · "),
                fontSize = 13.sp,
                color = MiPalette.inkMuted,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.padding(top = 3.dp)
            )
        }
        Spacer(modifier = Modifier.width(8.dp))
        Column(horizontalAlignment = Alignment.End) {
            Text(
                text = compactCurrency(a.totalAmount, symbol = currencySymbol(a.currency)),
                fontSize = 17.sp,
                fontWeight = FontWeight.SemiBold,
                color = MiPalette.ink
            )
            Spacer(modifier = Modifier.height(5.dp))
            StatusTag(text = "Level ${a.level}", color = MiPalette.warning)
        }
    }
}

private fun currencySymbol(code: String): String = when (code.uppercase()) {
    "PHP", "" -> "₱"
    "USD" -> "$"
    else -> "$code "
}
