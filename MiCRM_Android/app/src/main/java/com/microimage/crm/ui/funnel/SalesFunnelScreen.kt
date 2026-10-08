package com.microimage.crm.ui.funnel

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.navigation.NavController
import com.microimage.crm.api.RetrofitClient
import com.microimage.crm.model.SalesFunnel
import com.microimage.crm.ui.Screen
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
    // null = All stages; otherwise a FunnelStageStyle.key ("quoted", "closable"…).
    var selectedStage by remember { mutableStateOf<String?>(null) }

    fun load(stage: String?) {
        isLoading = true
        scope.launch {
            try {
                val response = RetrofitClient.apiService.getSalesFunnel("Token $token", stage)
                if (response.isSuccessful) {
                    funnelEntries = response.body() ?: emptyList()
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

    LaunchedEffect(Unit) { load(null) }

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
        Column(
            modifier = Modifier
                .padding(padding)
                .fillMaxSize()
                .background(MiPalette.canvas)
        ) {
            StageFilterRow(
                selectedStage = selectedStage,
                onSelect = { stage ->
                    selectedStage = stage
                    load(stage)
                }
            )

            Box(modifier = Modifier.fillMaxSize()) {
                if (isLoading) {
                    CircularProgressIndicator(modifier = Modifier.align(Alignment.Center), color = MiPalette.brand)
                } else if (errorMessage != null) {
                    Text(errorMessage!!, modifier = Modifier.align(Alignment.Center), color = MiPalette.inkMuted)
                } else {
                    FunnelList(funnelEntries) { entry ->
                        navController.navigate(Screen.FunnelDetail.createRoute(token, entry.id))
                    }
                }
            }
        }
    }
}

/**
 * Horizontal, scrollable row of stage filter chips mirroring the iOS funnel:
 * "All stages", then one chip per pipeline stage. The selected chip is filled
 * with its stage colour; the rest are tinted outlines.
 */
@Composable
private fun StageFilterRow(selectedStage: String?, onSelect: (String?) -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .horizontalScroll(rememberScrollState())
            .padding(horizontal = 20.dp, vertical = 12.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        StageChip(
            label = "All stages",
            color = MiPalette.inkMuted,
            isSelected = selectedStage == null,
            onClick = { onSelect(null) }
        )
        FunnelStageStyle.values().forEach { stage ->
            StageChip(
                label = stage.shortLabel,
                color = stage.color,
                isSelected = selectedStage == stage.key,
                onClick = { onSelect(stage.key) }
            )
        }
    }
}

@Composable
private fun StageChip(label: String, color: Color, isSelected: Boolean, onClick: () -> Unit) {
    Text(
        text = label,
        fontSize = 13.sp,
        fontWeight = FontWeight.Medium,
        color = if (isSelected) Color.White else color,
        maxLines = 1,
        modifier = Modifier
            .clip(RoundedCornerShape(50))
            .background(if (isSelected) color else color.copy(alpha = 0.12f))
            .clickable { onClick() }
            .padding(horizontal = 14.dp, vertical = 8.dp)
    )
}

@Composable
private fun FunnelList(entries: List<SalesFunnel>, onEntryClick: (SalesFunnel) -> Unit) {
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
                    Box(modifier = Modifier.clickable { onEntryClick(entry) }) {
                    PlainRow(
                        title = entry.companyName,
                        subtitle = entry.requirementDescription?.takeIf { it.isNotBlank() } ?: entry.stage,
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
}
