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
import com.microimage.crm.model.Proposal
import com.microimage.crm.ui.Screen
import com.microimage.crm.ui.theme.Hairline
import com.microimage.crm.ui.theme.MiPalette
import com.microimage.crm.ui.theme.RowCard
import com.microimage.crm.ui.theme.StatusColors
import com.microimage.crm.ui.theme.StatusTag
import com.microimage.crm.ui.theme.compactCurrency
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SalesProposalScreen(token: String, navController: NavController) {
    val scope = rememberCoroutineScope()
    var proposals by remember { mutableStateOf<List<Proposal>>(emptyList()) }
    var isLoading by remember { mutableStateOf(true) }
    var errorMessage by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(Unit) {
        scope.launch {
            try {
                val response = RetrofitClient.apiService.getProposals("Token $token")
                if (response.isSuccessful) {
                    proposals = response.body() ?: emptyList()
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
                title = { Text("Proposals") },
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
            if (isLoading) {
                CircularProgressIndicator(modifier = Modifier.align(Alignment.Center), color = MiPalette.brand)
            } else if (errorMessage != null) {
                Text(errorMessage!!, modifier = Modifier.align(Alignment.Center), color = MiPalette.inkMuted)
            } else {
                ProposalList(proposals) { proposal ->
                    navController.navigate(Screen.ProposalDetail.createRoute(token, proposal.id))
                }
            }
        }
    }
}

@Composable
private fun ProposalList(proposals: List<Proposal>, onClick: (Proposal) -> Unit) {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(horizontal = 20.dp, vertical = 16.dp)
    ) {
        item {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(bottom = 12.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = "${proposals.size} ${if (proposals.size == 1) "proposal" else "proposals"}",
                    fontSize = 15.sp,
                    color = MiPalette.inkMuted
                )
            }
        }

        item {
            RowCard {
                proposals.forEachIndexed { index, proposal ->
                    if (index > 0) Hairline()
                    ProposalRow(proposal) { onClick(proposal) }
                }
            }
        }
    }
}

@Composable
private fun ProposalRow(proposal: Proposal, onClick: () -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clickable { onClick() }
            .padding(vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Column(modifier = Modifier.weight(1f)) {
            Text(
                text = proposal.subject,
                fontSize = 16.sp,
                fontWeight = FontWeight.Medium,
                color = MiPalette.ink,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis
            )
            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier.padding(top = 3.dp)
            ) {
                Text(
                    text = proposal.proposalNumber,
                    fontSize = 13.sp,
                    color = MiPalette.inkFaint,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis
                )
                if (proposal.customerName.isNotBlank()) {
                    Spacer(modifier = Modifier.width(6.dp))
                    Text(
                        text = proposal.customerName,
                        fontSize = 13.sp,
                        color = MiPalette.inkMuted,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                        modifier = Modifier.weight(1f, fill = false)
                    )
                }
            }
        }
        Spacer(modifier = Modifier.width(8.dp))
        Column(horizontalAlignment = Alignment.End) {
            Text(
                text = compactCurrency(proposal.totalAmount, symbol = currencySymbol(proposal.currency)),
                fontSize = 17.sp,
                fontWeight = FontWeight.SemiBold,
                color = MiPalette.ink
            )
            Spacer(modifier = Modifier.height(5.dp))
            StatusTag(
                text = StatusColors.label(proposal.status),
                color = StatusColors.color(proposal.status)
            )
        }
    }
}

private fun currencySymbol(code: String): String = when (code.uppercase()) {
    "PHP", "" -> "₱"
    "USD" -> "$"
    else -> "$code "
}
