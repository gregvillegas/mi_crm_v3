package com.microimage.crm.ui.campaign

import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Toast
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Cancel
import androidx.compose.material.icons.filled.Preview
import androidx.compose.material.icons.filled.Send
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.navigation.NavController
import com.microimage.crm.api.RetrofitClient
import com.microimage.crm.model.CampaignPreview
import com.microimage.crm.model.CampaignSummary
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CampaignListScreen(token: String, navController: NavController) {
    val scope = rememberCoroutineScope()
    val context = LocalContext.current
    var campaigns by remember { mutableStateOf<List<CampaignSummary>>(emptyList()) }
    var isLoading by remember { mutableStateOf(true) }
    var errorMessage by remember { mutableStateOf<String?>(null) }
    
    var previewData by remember { mutableStateOf<CampaignPreview?>(null) }
    var showPreviewDialog by remember { mutableStateOf(false) }

    fun loadCampaigns() {
        isLoading = true
        scope.launch {
            try {
                val response = RetrofitClient.apiService.getCampaigns("Token $token")
                if (response.isSuccessful) {
                    campaigns = response.body() ?: emptyList()
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

    LaunchedEffect(Unit) { loadCampaigns() }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Email Campaigns") },
                navigationIcon = {
                    IconButton(onClick = { navController.popBackStack() }) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                    }
                }
            )
        }
    ) { padding ->
        Box(modifier = Modifier.padding(padding).fillMaxSize()) {
            if (isLoading) {
                CircularProgressIndicator(modifier = Modifier.align(Alignment.Center))
            } else if (errorMessage != null) {
                Text(errorMessage!!, modifier = Modifier.align(Alignment.Center))
            } else if (campaigns.isEmpty()) {
                Text("No campaigns found", modifier = Modifier.align(Alignment.Center))
            } else {
                LazyColumn(
                    contentPadding = PaddingValues(16.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    items(campaigns) { campaign ->
                        CampaignCard(
                            campaign = campaign,
                            onPreview = {
                                scope.launch {
                                    try {
                                        val res = RetrofitClient.apiService.previewCampaign("Token $token", campaign.id)
                                        if (res.isSuccessful && res.body() != null) {
                                            previewData = res.body()
                                            showPreviewDialog = true
                                        } else {
                                            Toast.makeText(context, "Preview failed: ${res.code()}", Toast.LENGTH_SHORT).show()
                                        }
                                    } catch (e: Exception) {
                                        Toast.makeText(context, "Error: ${e.message}", Toast.LENGTH_SHORT).show()
                                    }
                                }
                            },
                            onSend = {
                                scope.launch {
                                    val res = RetrofitClient.apiService.sendCampaign("Token $token", campaign.id)
                                    if (res.isSuccessful) {
                                        Toast.makeText(context, "Sending...", Toast.LENGTH_SHORT).show()
                                        loadCampaigns()
                                    }
                                }
                            },
                            onCancel = {
                                scope.launch {
                                    val res = RetrofitClient.apiService.cancelCampaign("Token $token", campaign.id)
                                    if (res.isSuccessful) {
                                        Toast.makeText(context, "Cancelled", Toast.LENGTH_SHORT).show()
                                        loadCampaigns()
                                    }
                                }
                            }
                        )
                    }
                }
            }
        }
    }

    if (showPreviewDialog && previewData != null) {
        // Calculate the base URL for the WebView to resolve relative image paths
        // If baseUrl is https://micrm.microimageph.com/api/v1/, we want https://micrm.microimageph.com/
        val rootBaseUrl = RetrofitClient.baseUrl.substringBefore("/api/v1/") + "/"

        AlertDialog(
            onDismissRequest = { showPreviewDialog = false },
            title = { Text(previewData?.subject ?: "Campaign Preview", fontSize = 16.sp) },
            text = {
                Box(modifier = Modifier.fillMaxWidth().height(400.dp)) {
                    AndroidView(
                        factory = { ctx ->
                            WebView(ctx).apply {
                                webViewClient = WebViewClient()
                                settings.javaScriptEnabled = true
                                settings.loadWithOverviewMode = true
                                settings.useWideViewPort = true
                                loadDataWithBaseURL(rootBaseUrl, previewData?.renderedBody ?: "", "text/html", "UTF-8", null)
                            }
                        },
                        modifier = Modifier.fillMaxSize()
                    )
                }
            },
            confirmButton = {
                TextButton(onClick = { showPreviewDialog = false }) {
                    Text("Close")
                }
            }
        )
    }
}

@Composable
fun CampaignCard(
    campaign: CampaignSummary,
    onPreview: () -> Unit,
    onSend: () -> Unit,
    onCancel: () -> Unit
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(horizontalArrangement = Arrangement.SpaceBetween, modifier = Modifier.fillMaxWidth()) {
                Text(text = campaign.name, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                StatusChip(campaign.status)
            }
            Text(text = campaign.subject, style = MaterialTheme.typography.bodyMedium)
            Text(text = "Recipients: ${campaign.totalRecipients}", style = MaterialTheme.typography.bodySmall, color = Color.Gray)
            
            Spacer(modifier = Modifier.height(16.dp))
            
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedButton(onClick = onPreview, modifier = Modifier.weight(1f)) {
                    Icon(Icons.Default.Preview, contentDescription = null, modifier = Modifier.size(16.dp))
                    Spacer(modifier = Modifier.width(4.dp))
                    Text("Preview", fontSize = 12.sp)
                }
                
                if (campaign.status == "draft" || campaign.status == "scheduled") {
                    Button(onClick = onSend, modifier = Modifier.weight(1f), colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF2E7D32))) {
                        Icon(Icons.Default.Send, contentDescription = null, modifier = Modifier.size(16.dp))
                        Spacer(modifier = Modifier.width(4.dp))
                        Text("Send", fontSize = 12.sp)
                    }
                }
                
                if (campaign.status == "sending" || campaign.status == "scheduled") {
                    Button(onClick = onCancel, modifier = Modifier.weight(1f), colors = ButtonDefaults.buttonColors(containerColor = Color.Red)) {
                        Icon(Icons.Default.Cancel, contentDescription = null, modifier = Modifier.size(16.dp))
                        Spacer(modifier = Modifier.width(4.dp))
                        Text("Cancel", fontSize = 12.sp)
                    }
                }
            }
        }
    }
}

@Composable
fun StatusChip(status: String) {
    val color = when (status.lowercase()) {
        "sent" -> Color(0xFF2E7D32)
        "draft" -> Color.Gray
        "sending" -> Color(0xFF1976D2)
        "scheduled" -> Color(0xFFF57C00)
        else -> Color.Red
    }
    Surface(
        color = color.copy(alpha = 0.1f),
        shape = MaterialTheme.shapes.small,
        border = androidx.compose.foundation.BorderStroke(1.dp, color)
    ) {
        Text(
            text = status.uppercase(),
            modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp),
            style = MaterialTheme.typography.labelSmall,
            color = color,
            fontWeight = FontWeight.Bold
        )
    }
}
