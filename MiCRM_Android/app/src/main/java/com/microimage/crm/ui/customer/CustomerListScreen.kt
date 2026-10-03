package com.microimage.crm.ui.customer

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.navigation.NavController
import com.microimage.crm.api.RetrofitClient
import com.microimage.crm.model.CustomerSummary
import com.microimage.crm.ui.Screen
import com.microimage.crm.ui.theme.Hairline
import com.microimage.crm.ui.theme.MiPalette
import com.microimage.crm.ui.theme.Monogram
import com.microimage.crm.ui.theme.RowCard
import com.microimage.crm.ui.theme.StatusTag
import com.microimage.crm.ui.theme.companyInitials
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CustomerListScreen(token: String, navController: NavController) {
    val scope = rememberCoroutineScope()
    var customers by remember { mutableStateOf<List<CustomerSummary>>(emptyList()) }
    var isLoading by remember { mutableStateOf(true) }
    var errorMessage by remember { mutableStateOf<String?>(null) }
    var userRole by remember { mutableStateOf("") }

    // Segmented filter: false = "All I can see", true = "Assigned to me".
    var mineOnly by remember { mutableStateOf(false) }
    var search by remember { mutableStateOf("") }
    var searchJob by remember { mutableStateOf<Job?>(null) }

    val authHeader = "Token $token"

    suspend fun fetch() {
        errorMessage = null
        try {
            val q = search.trim().ifBlank { null }
            // "Assigned to me" (or a salesperson) uses the my-customers endpoint;
            // otherwise the full list the user is allowed to see.
            val response = if (mineOnly || userRole == "salesperson") {
                RetrofitClient.apiService.getMyCustomers(authHeader, q)
            } else {
                RetrofitClient.apiService.getCustomers(authHeader, q)
            }
            if (response.isSuccessful) {
                customers = response.body() ?: emptyList()
            } else if (response.code() == 404) {
                val fallback = RetrofitClient.apiService.getMyCustomers(authHeader, q)
                customers = if (fallback.isSuccessful) fallback.body() ?: emptyList() else emptyList()
                if (!fallback.isSuccessful) errorMessage = "Error: ${response.code()}"
            } else {
                errorMessage = "Error: ${response.code()}"
            }
        } catch (e: Exception) {
            errorMessage = e.message
        }
    }

    // Initial load: resolve role first (salespeople default to their own list).
    LaunchedEffect(Unit) {
        isLoading = true
        try {
            val userRes = RetrofitClient.apiService.getCurrentUser(authHeader)
            if (userRes.isSuccessful) userRole = userRes.body()?.role ?: ""
        } catch (_: Exception) { }
        fetch()
        isLoading = false
    }

    fun reload() {
        scope.launch {
            isLoading = true
            fetch()
            isLoading = false
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Customers") },
                navigationIcon = {
                    IconButton(onClick = { navController.popBackStack() }) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = MiPalette.surface)
            )
        },
        floatingActionButton = {
            FloatingActionButton(
                onClick = { navController.navigate(Screen.CustomerCreateRequest.createRoute(token)) },
                containerColor = MiPalette.brand,
                contentColor = androidx.compose.ui.graphics.Color.White,
                shape = RoundedCornerShape(16.dp)
            ) {
                Icon(Icons.Default.Add, contentDescription = "Request New Customer")
            }
        }
    ) { padding ->
        Column(
            modifier = Modifier
                .padding(padding)
                .fillMaxSize()
                .background(MiPalette.canvas)
        ) {
            // Scope filter (segmented) — hidden for salespeople who only have their own.
            if (userRole != "salesperson") {
                ScopeToggle(
                    mineOnly = mineOnly,
                    onChange = { mineOnly = it; reload() },
                    modifier = Modifier.padding(horizontal = 20.dp, vertical = 12.dp)
                )
            } else {
                Spacer(modifier = Modifier.height(12.dp))
            }

            // Search field
            OutlinedTextField(
                value = search,
                onValueChange = {
                    search = it
                    searchJob?.cancel()
                    searchJob = scope.launch {
                        delay(300) // debounce
                        fetch()
                    }
                },
                leadingIcon = { Icon(Icons.Default.Search, contentDescription = null, tint = MiPalette.inkFaint) },
                placeholder = { Text("Company, contact, or phone", color = MiPalette.inkFaint) },
                singleLine = true,
                shape = RoundedCornerShape(12.dp),
                colors = OutlinedTextFieldDefaults.colors(
                    focusedContainerColor = MiPalette.surface,
                    unfocusedContainerColor = MiPalette.surface,
                    focusedBorderColor = MiPalette.hairline,
                    unfocusedBorderColor = MiPalette.hairline
                ),
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 20.dp)
                    .padding(bottom = 8.dp)
            )

            Box(modifier = Modifier.fillMaxSize()) {
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
                    customers.isEmpty() -> Text(
                        if (search.isBlank()) "No customers found" else "Nothing matched \"$search\"",
                        modifier = Modifier.align(Alignment.Center),
                        color = MiPalette.inkMuted
                    )
                    else -> CustomerList(customers) { customer ->
                        navController.navigate(Screen.CustomerDetail.createRoute(token, customer.id))
                    }
                }
            }
        }
    }
}

@Composable
private fun ScopeToggle(mineOnly: Boolean, onChange: (Boolean) -> Unit, modifier: Modifier = Modifier) {
    Row(
        modifier = modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(10.dp))
            .background(MiPalette.hairline.copy(alpha = 0.6f))
            .padding(3.dp)
    ) {
        SegmentButton("All I can see", selected = !mineOnly, modifier = Modifier.weight(1f)) { onChange(false) }
        SegmentButton("Assigned to me", selected = mineOnly, modifier = Modifier.weight(1f)) { onChange(true) }
    }
}

@Composable
private fun SegmentButton(label: String, selected: Boolean, modifier: Modifier = Modifier, onClick: () -> Unit) {
    Box(
        modifier = modifier
            .clip(RoundedCornerShape(8.dp))
            .background(if (selected) MiPalette.surface else androidx.compose.ui.graphics.Color.Transparent)
            .clickable { onClick() }
            .padding(vertical = 8.dp),
        contentAlignment = Alignment.Center
    ) {
        Text(
            text = label,
            fontSize = 13.sp,
            fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Normal,
            color = if (selected) MiPalette.ink else MiPalette.inkMuted
        )
    }
}

@Composable
private fun CustomerList(customers: List<CustomerSummary>, onClick: (CustomerSummary) -> Unit) {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(horizontal = 20.dp, vertical = 8.dp)
    ) {
        item {
            RowCard {
                customers.forEachIndexed { index, customer ->
                    if (index > 0) Hairline()
                    CustomerRow(customer) { onClick(customer) }
                }
            }
        }
        item {
            Text(
                text = "${customers.size} ${if (customers.size == 1) "customer" else "customers"}",
                fontSize = 13.sp,
                color = MiPalette.inkFaint,
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(vertical = 14.dp),
                textAlign = androidx.compose.ui.text.style.TextAlign.Center
            )
        }
    }
}

@Composable
private fun CustomerRow(customer: CustomerSummary, onClick: () -> Unit) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clickable { onClick() }
            .padding(vertical = 11.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Monogram(companyInitials(customer.companyName))
        Spacer(modifier = Modifier.width(12.dp))
        Column(modifier = Modifier.weight(1f)) {
            Text(
                text = customer.companyName,
                fontSize = 16.sp,
                fontWeight = FontWeight.Medium,
                color = MiPalette.ink,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis
            )
            Text(
                text = customer.contactPersonName,
                fontSize = 13.sp,
                color = MiPalette.inkMuted,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.padding(top = 3.dp)
            )
        }
        Spacer(modifier = Modifier.width(8.dp))
        if (customer.isMillionaireAccount) {
            StatusTag(text = "Key", color = MiPalette.positive)
        } else if (customer.autoInactiveFlag) {
            StatusTag(text = "Dormant", color = MiPalette.warning)
        }
    }
}
