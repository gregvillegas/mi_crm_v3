package com.microimage.crm.ui.funnel

import androidx.compose.foundation.background
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
import com.microimage.crm.model.SalesFunnel
import com.microimage.crm.ui.theme.FunnelStageStyle
import com.microimage.crm.ui.theme.Hairline
import com.microimage.crm.ui.theme.MiPalette
import com.microimage.crm.ui.theme.PlainRow
import com.microimage.crm.ui.theme.RowCard
import com.microimage.crm.ui.theme.compactCurrency
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SalesFunnelScreen(token: String, navController: NavController) {
    val scope = rememberCoroutineScope()
    var funnelEntries by remember { mutableStateOf<List<SalesFunnel>>(emptyList()) }
    var isLoading by remember { mutableStateOf(true) }
    var errorMessage by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(Unit) {
        scope.launch {
            try {
                val response = RetrofitClient.apiService.getSalesFunnel("Token $token")
                if (response.isSuccessful) {
                    funnelEntries = response.body() ?: emptyList()
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
                title = { Text("Funnel") },
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
                FunnelList(funnelEntries)
            }
        }
    }
}

@Composable
private fun FunnelList(entries: List<SalesFunnel>) {
    val total = entries.sumOf { it.retail }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(horizontal = 20.dp, vertical = 16.dp)
    ) {
        // Count + total header, mirroring the iOS "495 deals  ₱601,600,987" line.
        item {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(bottom = 12.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = "${entries.size} ${if (entries.size == 1) "deal" else "deals"}",
                    fontSize = 15.sp,
                    color = MiPalette.inkMuted
                )
                Spacer(modifier = Modifier.weight(1f))
                Text(
                    text = compactCurrency(total),
                    fontSize = 18.sp,
                    fontWeight = FontWeight.SemiBold,
                    color = MiPalette.ink
                )
            }
        }

        item {
            RowCard {
                entries.forEachIndexed { index, entry ->
                    if (index > 0) Hairline()
                    val style = FunnelStageStyle.from(entry.stage)
                    PlainRow(
                        title = entry.companyName,
                        subtitle = entry.stage,
                        accent = style.color
                    ) {
                        Column(horizontalAlignment = Alignment.End) {
                            Text(
                                text = compactCurrency(entry.retail),
                                fontSize = 17.sp,
                                fontWeight = FontWeight.SemiBold,
                                color = MiPalette.ink
                            )
                            Text(
                                text = entry.stage,
                                fontSize = 11.sp,
                                fontWeight = FontWeight.Medium,
                                color = style.color,
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis,
                                modifier = Modifier.padding(top = 4.dp)
                            )
                        }
                    }
                }
            }
        }
    }
}
