package com.microimage.crm.ui.dashboard

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.navigation.NavController
import com.microimage.crm.api.RetrofitClient
import com.microimage.crm.model.DashboardSummary
import com.microimage.crm.model.FunnelStage
import com.microimage.crm.model.Proposal
import com.microimage.crm.model.SalesActivity
import com.microimage.crm.model.SalesFunnel
import com.microimage.crm.ui.Screen
import com.microimage.crm.ui.theme.MiRed
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DashboardScreen(token: String, navController: NavController) {
    val scope = rememberCoroutineScope()
    val drawerState = rememberDrawerState(initialValue = DrawerValue.Closed)
    
    var summary by remember { mutableStateOf<DashboardSummary?>(null) }
    var isLoading by remember { mutableStateOf(true) }
    var errorMessage by remember { mutableStateOf<String?>(null) }
    var reloadKey by remember { mutableIntStateOf(0) }
    var showProfileMenu by remember { mutableStateOf(false) }
    var showSignOutDialog by remember { mutableStateOf(false) }
    var isSigningOut by remember { mutableStateOf(false) }

    // One aggregated call. This screen used to pull the full funnel, proposal
    // and activity lists and reduce them on-device.
    LaunchedEffect(reloadKey) {
        isLoading = true
        errorMessage = null
        try {
            val response = RetrofitClient.apiService.getDashboard("Token $token")
            if (response.isSuccessful && response.body() != null) {
                summary = response.body()
            } else {
                errorMessage = when (response.code()) {
                    401, 403 -> "Your session has expired. Please sign in again."
                    404 -> "The dashboard endpoint is missing on this server. " +
                        "It is likely running an older build — redeploy the CRM, then retry."
                    else -> "Failed to load dashboard (${response.code()})"
                }
            }
        } catch (e: Exception) {
            errorMessage = "Failed to load data: ${e.message}"
        } finally {
            isLoading = false
        }
    }

    // Best effort token revocation. A failure here (offline, or a server build
    // without the logout endpoint) must never trap the user inside the app, so
    // we drop back to Login either way.
    fun signOut() {
        if (isSigningOut) return
        isSigningOut = true
        scope.launch {
            runCatching { RetrofitClient.apiService.logout("Token $token") }
            drawerState.close()
            navController.navigate(Screen.Login.route) {
                popUpTo(0) { inclusive = true }
            }
        }
    }

    val proposals = summary?.recentProposals ?: emptyList()
    val activities = summary?.upcomingActivities ?: emptyList()

    if (showSignOutDialog) {
        AlertDialog(
            onDismissRequest = { showSignOutDialog = false },
            title = { Text("Sign out?") },
            text = { Text("You will need to sign in again to use MiCRM.") },
            confirmButton = {
                TextButton(onClick = { showSignOutDialog = false; signOut() }) {
                    Text("Sign out", color = MiRed, fontWeight = FontWeight.Bold)
                }
            },
            dismissButton = {
                TextButton(onClick = { showSignOutDialog = false }) { Text("Cancel") }
            }
        )
    }

    ModalNavigationDrawer(
        drawerState = drawerState,
        drawerContent = {
            ModalDrawerSheet {
                DrawerHeader(summary)
                Divider()
                Spacer(modifier = Modifier.height(8.dp))
                DrawerItem(Icons.Default.GridView, "Dashboard", selected = true) {
                    scope.launch { drawerState.close() }
                }
                DrawerItem(Icons.Default.Group, "Customers") {
                    scope.launch { drawerState.close() }
                    navController.navigate(Screen.CustomerList.createRoute(token))
                }
                DrawerItem(Icons.Default.Description, "Proposals") {
                    scope.launch { drawerState.close() }
                    navController.navigate(Screen.SalesProposal.createRoute(token))
                }
                DrawerItem(
                    Icons.Default.FactCheck,
                    "Approvals",
                    badgeCount = summary?.proposals?.myPendingApprovals ?: 0
                ) {
                    scope.launch { drawerState.close() }
                    navController.navigate(Screen.PendingProposalApprovals.createRoute(token))
                }
                DrawerItem(Icons.Default.FilterList, "Sales Funnel") {
                    scope.launch { drawerState.close() }
                    navController.navigate(Screen.SalesFunnel.createRoute(token))
                }
                DrawerItem(Icons.Default.Campaign, "Campaigns") {
                    scope.launch { drawerState.close() }
                    navController.navigate(Screen.CampaignList.createRoute(token))
                }

                Spacer(modifier = Modifier.weight(1f))
                Divider(modifier = Modifier.padding(vertical = 8.dp))
                DrawerItem(Icons.Default.Settings, "Settings") {
                    scope.launch { drawerState.close() }
                    navController.navigate(Screen.Settings.createRoute(token))
                }
                DrawerItem(Icons.Default.ExitToApp, "Sign out", tint = MiRed) {
                    showSignOutDialog = true
                }
                Spacer(modifier = Modifier.height(12.dp))
            }
        }
    ) {
        Scaffold(
            topBar = {
                TopAppBar(
                    title = {
                        Text(
                            text = "MiCRM",
                            color = MiRed,
                            fontWeight = FontWeight.Bold,
                            fontStyle = FontStyle.Italic,
                            fontSize = 22.sp
                        )
                    },
                    navigationIcon = {
                        IconButton(onClick = { scope.launch { drawerState.open() } }) {
                            Icon(Icons.Default.Menu, contentDescription = "Menu", tint = MiRed)
                        }
                    },
                    actions = {
                        IconButton(onClick = { navController.navigate(Screen.CustomerList.createRoute(token)) }) {
                            Icon(Icons.Default.Search, contentDescription = "Search", tint = Color.DarkGray)
                        }
                        Box {
                            Box(
                                modifier = Modifier
                                    .padding(end = 12.dp)
                                    .size(36.dp)
                                    .clip(CircleShape)
                                    .background(Color(0xFFE2E8F0))
                                    .clickable { showProfileMenu = true }
                            ) {
                                val initials = summary?.user?.initials.orEmpty()
                                if (initials.isNotBlank()) {
                                    Text(
                                        text = initials,
                                        modifier = Modifier.align(Alignment.Center),
                                        fontSize = 13.sp,
                                        fontWeight = FontWeight.Bold,
                                        color = Color(0xFF475569)
                                    )
                                } else {
                                    Icon(
                                        Icons.Default.Person,
                                        contentDescription = "Profile",
                                        tint = Color.Gray,
                                        modifier = Modifier.align(Alignment.Center).size(24.dp)
                                    )
                                }
                            }
                            DropdownMenu(
                                expanded = showProfileMenu,
                                onDismissRequest = { showProfileMenu = false }
                            ) {
                                summary?.user?.let { user ->
                                    Column(modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp)) {
                                        Text(user.name, fontWeight = FontWeight.Bold, fontSize = 14.sp, color = Color(0xFF0F172A))
                                        Text(user.roleDisplay, fontSize = 12.sp, color = Color.Gray)
                                    }
                                    Divider()
                                }
                                DropdownMenuItem(
                                    text = { Text("Settings") },
                                    leadingIcon = { Icon(Icons.Default.Settings, contentDescription = null) },
                                    onClick = {
                                        showProfileMenu = false
                                        navController.navigate(Screen.Settings.createRoute(token))
                                    }
                                )
                                DropdownMenuItem(
                                    text = { Text("Sign out", color = MiRed, fontWeight = FontWeight.Bold) },
                                    leadingIcon = { Icon(Icons.Default.ExitToApp, contentDescription = null, tint = MiRed) },
                                    onClick = {
                                        showProfileMenu = false
                                        showSignOutDialog = true
                                    }
                                )
                            }
                        }
                    },
                    colors = TopAppBarDefaults.topAppBarColors(containerColor = Color.White)
                )
            },
            bottomBar = {
                MiBottomNavigation(
                    navController,
                    token,
                    pendingApprovals = summary?.proposals?.myPendingApprovals ?: 0
                )
            },
            floatingActionButton = {
                FloatingActionButton(
                    onClick = { navController.navigate(Screen.SalesActivityCreate.createRoute(token)) },
                    containerColor = Color(0xFF991B1B),
                    contentColor = Color.White,
                    shape = RoundedCornerShape(12.dp),
                    modifier = Modifier.padding(bottom = 8.dp)
                ) {
                    Icon(Icons.Default.Add, contentDescription = "Add")
                }
            }
        ) { paddingValues ->
            Box(modifier = Modifier.padding(paddingValues).fillMaxSize().background(com.microimage.crm.ui.theme.MiPalette.canvas)) {
                if (isLoading) {
                    CircularProgressIndicator(modifier = Modifier.align(Alignment.Center), color = MiRed)
                } else if (errorMessage != null) {
                    Column(
                        modifier = Modifier.align(Alignment.Center).padding(32.dp),
                        horizontalAlignment = Alignment.CenterHorizontally
                    ) {
                        Icon(
                            Icons.Default.CloudOff,
                            contentDescription = null,
                            tint = Color(0xFF94A3B8),
                            modifier = Modifier.size(48.dp)
                        )
                        Spacer(modifier = Modifier.height(12.dp))
                        Text(
                            text = errorMessage!!,
                            color = Color(0xFF475569),
                            textAlign = TextAlign.Center,
                            fontSize = 14.sp
                        )
                        Spacer(modifier = Modifier.height(16.dp))
                        Button(
                            onClick = { reloadKey++ },
                            colors = ButtonDefaults.buttonColors(containerColor = MiRed)
                        ) {
                            Icon(Icons.Default.Refresh, contentDescription = null, modifier = Modifier.size(18.dp))
                            Spacer(modifier = Modifier.width(8.dp))
                            Text("Retry")
                        }
                        TextButton(onClick = { showSignOutDialog = true }) {
                            Text("Sign out", color = MiRed)
                        }
                    }
                } else {
                    DashboardContent(
                        summary = summary,
                        proposals = proposals,
                        activities = activities,
                        onApprovals = { navController.navigate(Screen.PendingProposalApprovals.createRoute(token)) },
                        onRequests = { navController.navigate(Screen.PendingCustomerRequests.createRoute(token)) },
                        onViewAllProposals = { navController.navigate(Screen.SalesProposal.createRoute(token)) },
                        onProposalClick = { p -> navController.navigate(Screen.ProposalDetail.createRoute(token, p.id)) }
                    )
                }
            }
        }
    }
}

// iOS-style dashboard body: pipeline rail, "Needs you" prompts, Coming up,
// Recent proposals, and a "Your book" metrics card. Replaces the old wrapping
// KPI tiles + horizontal funnel cards.
@Composable
private fun DashboardContent(
    summary: DashboardSummary?,
    proposals: List<Proposal>,
    activities: List<SalesActivity>,
    onApprovals: () -> Unit,
    onRequests: () -> Unit,
    onViewAllProposals: () -> Unit,
    onProposalClick: (Proposal) -> Unit,
) {
    val palette = com.microimage.crm.ui.theme.MiPalette
    val stageColors = mapOf(
        "quoted" to Color(0xFFD81B60),
        "closable" to Color(0xFFC77700),
        "project" to Color(0xFF1B7A4B),
        "services" to Color(0xFF0056B3),
    )

    androidx.compose.foundation.lazy.LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(horizontal = 20.dp, vertical = 16.dp),
        verticalArrangement = Arrangement.spacedBy(18.dp)
    ) {
        // Inspiration quote (same source as the web login quote: core/quotes.py).
        val quote = summary?.quote
        if (!quote.isNullOrBlank()) {
            item {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(14.dp))
                        .background(palette.surface)
                        .padding(16.dp),
                    verticalAlignment = Alignment.Top
                ) {
                    Icon(
                        Icons.Default.FormatQuote,
                        contentDescription = null,
                        tint = palette.brand,
                        modifier = Modifier.size(18.dp)
                    )
                    Spacer(modifier = Modifier.width(12.dp))
                    Text(
                        text = quote,
                        fontSize = 15.sp,
                        color = palette.ink
                    )
                }
            }
        }

        // Pipeline rail
        item {
            val stages = (summary?.funnel?.stages ?: emptyList()).map {
                com.microimage.crm.ui.theme.PipelineStage(
                    label = it.label,
                    count = it.count,
                    value = it.value,
                    color = stageColors[it.stage.lowercase()] ?: palette.inkFaint
                )
            }
            com.microimage.crm.ui.theme.PipelineRail(
                stages = stages,
                totalValue = summary?.funnel?.totalValue ?: 0.0
            )
        }

        // Needs you — only rendered when something is waiting.
        val approvalsCount = summary?.proposals?.myPendingApprovals ?: 0
        val requestsCount = summary?.customerRequests?.awaitingMyReview ?: 0
        if (approvalsCount > 0 || requestsCount > 0) {
            item {
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    com.microimage.crm.ui.theme.SectionHeading(title = "Needs you")
                    if (approvalsCount > 0) {
                        com.microimage.crm.ui.theme.ActionPrompt(
                            count = approvalsCount,
                            title = if (approvalsCount == 1) "Proposal to approve" else "Proposals to approve",
                            subtitle = "Waiting on your decision",
                            icon = Icons.Default.FactCheck,
                            onClick = onApprovals
                        )
                    }
                    if (requestsCount > 0) {
                        com.microimage.crm.ui.theme.ActionPrompt(
                            count = requestsCount,
                            title = if (requestsCount == 1) "New customer request" else "New customer requests",
                            subtitle = "Submitted by your team",
                            icon = Icons.Default.PersonAdd,
                            onClick = onRequests
                        )
                    }
                }
            }
        }

        // Coming up
        item {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                com.microimage.crm.ui.theme.SectionHeading(title = "Coming up")
                com.microimage.crm.ui.theme.RowCard {
                    if (activities.isEmpty()) {
                        Text(
                            "Nothing scheduled. Log an activity after your next visit.",
                            fontSize = 15.sp,
                            color = palette.inkMuted,
                            modifier = Modifier.fillMaxWidth().padding(vertical = 16.dp)
                        )
                    } else {
                        activities.take(3).forEachIndexed { index, a ->
                            if (index > 0) com.microimage.crm.ui.theme.Hairline()
                            com.microimage.crm.ui.theme.PlainRow(
                                title = a.title,
                                subtitle = listOfNotNull(a.customerName, a.scheduledStart).joinToString(" · ")
                            )
                        }
                    }
                }
            }
        }

        // Recent proposals
        if (proposals.isNotEmpty()) {
            item {
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    com.microimage.crm.ui.theme.SectionHeading(
                        title = "Recent proposals",
                        actionText = "View all",
                        onAction = onViewAllProposals
                    )
                    com.microimage.crm.ui.theme.RowCard {
                        proposals.take(5).forEachIndexed { index, p ->
                            if (index > 0) com.microimage.crm.ui.theme.Hairline()
                            androidx.compose.foundation.layout.Row(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .clickable { onProposalClick(p) }
                                    .padding(vertical = 12.dp),
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Column(modifier = Modifier.weight(1f)) {
                                    Text(p.subject, fontSize = 16.sp, fontWeight = FontWeight.Medium, color = palette.ink, maxLines = 1, overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis)
                                    Text(
                                        listOf(p.proposalNumber, p.customerName).filter { it.isNotBlank() }.joinToString(" · "),
                                        fontSize = 13.sp, color = palette.inkMuted, maxLines = 1,
                                        overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis,
                                        modifier = Modifier.padding(top = 3.dp)
                                    )
                                }
                                Spacer(modifier = Modifier.width(8.dp))
                                Text(
                                    com.microimage.crm.ui.theme.compactCurrency(
                                        p.totalAmount,
                                        symbol = if (p.currency.uppercase() == "USD") "$" else "₱"
                                    ),
                                    fontSize = 17.sp, fontWeight = FontWeight.SemiBold, color = palette.ink
                                )
                            }
                        }
                    }
                }
            }
        }

        // Your book — metrics that used to wrap as KPI tiles.
        summary?.let { data ->
            item {
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    com.microimage.crm.ui.theme.SectionHeading(title = "Your book")
                    com.microimage.crm.ui.theme.RowCard {
                        com.microimage.crm.ui.theme.MetricRow("Customers", data.customers.total.toString())
                        com.microimage.crm.ui.theme.Hairline()
                        com.microimage.crm.ui.theme.MetricRow("Proposals this month", data.proposals.thisMonth.toString())
                        com.microimage.crm.ui.theme.Hairline()
                        com.microimage.crm.ui.theme.MetricRow("Activities completed this month", data.activities.completedThisMonth.toString())
                        com.microimage.crm.ui.theme.Hairline()
                        com.microimage.crm.ui.theme.MetricRow("Overdue activities", data.activities.overdue.toString())
                    }
                }
            }
        }
    }
}

@Composable
private fun DrawerHeader(summary: DashboardSummary?) {
    Row(
        modifier = Modifier.fillMaxWidth().padding(20.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Box(
            modifier = Modifier.size(44.dp).clip(CircleShape).background(Color(0xFFFFEDEB))
        ) {
            Text(
                text = summary?.user?.initials?.takeIf { it.isNotBlank() } ?: "MI",
                modifier = Modifier.align(Alignment.Center),
                fontSize = 15.sp,
                fontWeight = FontWeight.Bold,
                color = MiRed
            )
        }
        Spacer(modifier = Modifier.width(12.dp))
        Column {
            Text(
                text = summary?.user?.name ?: "MiCRM",
                fontSize = 16.sp,
                fontWeight = FontWeight.Bold,
                color = Color(0xFF0F172A),
                maxLines = 1
            )
            Text(
                text = summary?.user?.roleDisplay ?: "Menu",
                fontSize = 12.sp,
                color = Color.Gray,
                maxLines = 1
            )
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun DrawerItem(
    icon: ImageVector,
    label: String,
    selected: Boolean = false,
    badgeCount: Int = 0,
    tint: Color? = null,
    onClick: () -> Unit
) {
    val contentColor = tint ?: if (selected) MiRed else Color(0xFF334155)
    NavigationDrawerItem(
        icon = { Icon(icon, contentDescription = null, tint = contentColor) },
        label = {
            Text(
                label,
                color = contentColor,
                fontWeight = if (selected) FontWeight.Bold else FontWeight.Normal
            )
        },
        badge = {
            if (badgeCount > 0) {
                Badge(containerColor = MiRed, contentColor = Color.White) {
                    Text(badgeCount.toString(), fontSize = 10.sp)
                }
            }
        },
        selected = selected,
        onClick = onClick,
        modifier = Modifier.padding(horizontal = 12.dp)
    )
}

@Composable
fun SectionHeader(title: String, actionText: String? = null, onActionClick: (() -> Unit)? = null) {
    Row(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 12.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(text = title, fontSize = 20.sp, fontWeight = FontWeight.Black, color = Color(0xFF0F172A))
        if (actionText != null) {
            Text(
                text = actionText,
                fontSize = 11.sp,
                fontWeight = FontWeight.Bold,
                color = Color(0xFF991B1B),
                modifier = Modifier.clickable { onActionClick?.invoke() }
            )
        }
    }
}

@Composable
fun FunnelCard(item: SalesFunnel) {
    Card(
        modifier = Modifier.width(260.dp).fillMaxHeight(),
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = Color(0xFFD9EFFF))
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Column {
                    Text(text = item.stage.uppercase(), fontSize = 11.sp, fontWeight = FontWeight.Bold, color = Color(0xFF991B1B).copy(alpha = 0.7f))
                    Text(text = "PHP ${formatAmount(item.retail)}", fontSize = 22.sp, fontWeight = FontWeight.Black, color = Color(0xFF0F172A))
                }
                Surface(modifier = Modifier.size(36.dp), shape = RoundedCornerShape(8.dp), color = Color.White.copy(alpha = 0.5f)) {
                    Icon(Icons.Default.FilterList, contentDescription = null, tint = Color(0xFF991B1B), modifier = Modifier.padding(6.dp))
                }
            }
            Spacer(modifier = Modifier.weight(1f))
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(text = "OPPORTUNITIES", fontSize = 10.sp, fontWeight = FontWeight.Bold, color = Color(0xFF475569))
                Text(text = "${item.probability}%", fontSize = 10.sp, fontWeight = FontWeight.Bold, color = Color(0xFF991B1B))
            }
            Spacer(modifier = Modifier.height(4.dp))
            LinearProgressIndicator(
                progress = item.probability / 100f,
                modifier = Modifier.fillMaxWidth().height(8.dp).clip(CircleShape),
                color = Color(0xFF991B1B),
                trackColor = Color.White.copy(alpha = 0.5f)
            )
        }
    }
}

@Composable
fun MockFunnelCard(stage: String, value: String, count: Int, progress: Int) {
    Card(
        modifier = Modifier.width(260.dp).fillMaxHeight(),
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = Color(0xFFD9EFFF))
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Column {
                    Text(text = stage, fontSize = 11.sp, fontWeight = FontWeight.Bold, color = Color(0xFF991B1B).copy(alpha = 0.7f))
                    Text(text = "PHP $value", fontSize = 22.sp, fontWeight = FontWeight.Black, color = Color(0xFF0F172A))
                }
                Surface(modifier = Modifier.size(36.dp), shape = RoundedCornerShape(8.dp), color = Color.White.copy(alpha = 0.5f)) {
                    Icon(Icons.Default.FilterList, contentDescription = null, tint = Color(0xFF991B1B), modifier = Modifier.padding(6.dp))
                }
            }
            Spacer(modifier = Modifier.weight(1f))
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(text = "$count OPPORTUNITIES", fontSize = 10.sp, fontWeight = FontWeight.Bold, color = Color(0xFF475569))
                Text(text = "$progress%", fontSize = 10.sp, fontWeight = FontWeight.Bold, color = Color(0xFF991B1B))
            }
            Spacer(modifier = Modifier.height(4.dp))
            LinearProgressIndicator(
                progress = progress / 100f,
                modifier = Modifier.fillMaxWidth().height(8.dp).clip(CircleShape),
                color = Color(0xFF991B1B),
                trackColor = Color.White.copy(alpha = 0.5f)
            )
        }
    }
}

@Composable
fun ProposalCard(item: Proposal, onClick: () -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 6.dp).clickable { onClick() },
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(containerColor = Color.White),
        elevation = CardDefaults.cardElevation(defaultElevation = 0.dp)
    ) {
        Row(modifier = Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
            Column(modifier = Modifier.weight(1f)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Surface(color = Color(0xFFF1F5F9), shape = RoundedCornerShape(4.dp)) {
                        Text(text = "#${item.proposalNumber}", modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp), fontSize = 10.sp, fontWeight = FontWeight.Bold, color = Color(0xFF991B1B))
                    }
                    Spacer(modifier = Modifier.width(8.dp))
                    Text(text = item.subject, fontWeight = FontWeight.Bold, fontSize = 14.sp, color = Color(0xFF1E293B))
                }
                Text(text = item.customerName, fontSize = 12.sp, color = Color.Gray, modifier = Modifier.padding(top = 4.dp))
            }
            Column(horizontalAlignment = Alignment.End) {
                Text(text = "PHP ${formatAmount(item.totalAmount)}", fontWeight = FontWeight.Black, fontSize = 14.sp, color = Color(0xFF0F172A))
                Surface(
                    modifier = Modifier.padding(top = 4.dp),
                    color = if (item.status.contains("Accepted", true)) Color(0xFFD9F9E6) else Color(0xFFFFEDEB),
                    shape = RoundedCornerShape(4.dp)
                ) {
                    Text(
                        text = item.status.uppercase(),
                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 2.dp),
                        fontSize = 9.sp,
                        fontWeight = FontWeight.Black,
                        color = if (item.status.contains("Accepted", true)) Color(0xFF059669) else Color(0xFFEF4444)
                    )
                }
            }
        }
    }
}

@Composable
fun MockProposalCard(id: String, title: String, client: String, value: String, status: String) {
    Card(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 6.dp),
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(containerColor = Color.White)
    ) {
        Row(modifier = Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
            Column(modifier = Modifier.weight(1f)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Surface(color = Color(0xFFF1F5F9), shape = RoundedCornerShape(4.dp)) {
                        Text(text = "#$id", modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp), fontSize = 10.sp, fontWeight = FontWeight.Bold, color = Color(0xFF991B1B))
                    }
                    Spacer(modifier = Modifier.width(8.dp))
                    Text(text = title, fontWeight = FontWeight.Bold, fontSize = 14.sp, color = Color(0xFF1E293B))
                }
                Text(text = client, fontSize = 12.sp, color = Color.Gray, modifier = Modifier.padding(top = 4.dp))
            }
            Column(horizontalAlignment = Alignment.End) {
                Text(text = "PHP $value", fontWeight = FontWeight.Black, fontSize = 14.sp, color = Color(0xFF0F172A))
                Surface(
                    modifier = Modifier.padding(top = 4.dp),
                    color = if (status == "ACCEPTED") Color(0xFFD9F9E6) else Color(0xFFFFEDEB),
                    shape = RoundedCornerShape(4.dp)
                ) {
                    Text(
                        text = status,
                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 2.dp),
                        fontSize = 9.sp,
                        fontWeight = FontWeight.Black,
                        color = if (status == "ACCEPTED") Color(0xFF059669) else Color(0xFFEF4444)
                    )
                }
            }
        }
    }
}

@Composable
fun ActivityCard(item: SalesActivity) {
    Card(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp),
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = Color(0xFFEDF8FF))
    ) {
        Row(modifier = Modifier.padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
            Surface(modifier = Modifier.size(50.dp), shape = RoundedCornerShape(12.dp), color = Color.White) {
                Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
                    Text(text = "OCT", fontSize = 9.sp, fontWeight = FontWeight.Bold, color = Color(0xFF991B1B))
                    Text(text = "24", fontSize = 18.sp, fontWeight = FontWeight.Black, color = Color(0xFF0F172A))
                }
            }
            Spacer(modifier = Modifier.width(12.dp))
            Column(modifier = Modifier.weight(1f)) {
                Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    Text(text = item.title, fontWeight = FontWeight.Bold, fontSize = 14.sp, color = Color(0xFF1E293B))
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Default.AccessTime, contentDescription = null, modifier = Modifier.size(12.dp), tint = Color.Gray)
                        Text(text = " 14:00", fontSize = 10.sp, color = Color.Gray, fontWeight = FontWeight.Bold)
                    }
                }
                Text(text = item.customerName ?: "Internal", fontSize = 12.sp, color = Color.Gray)
                Spacer(modifier = Modifier.height(8.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Row {
                        repeat(2) { Box(modifier = Modifier.size(20.dp).clip(CircleShape).background(Color.Gray).offset(x = (it * -8).dp)) }
                    }
                    Spacer(modifier = Modifier.weight(1f))
                    Surface(color = Color(0xFFFFEDEB), shape = RoundedCornerShape(12.dp)) {
                        Text(text = item.status.uppercase(), modifier = Modifier.padding(horizontal = 10.dp, vertical = 4.dp), fontSize = 9.sp, fontWeight = FontWeight.Bold, color = Color(0xFF991B1B))
                    }
                }
            }
        }
    }
}

@Composable
fun MockActivityCard(day: String, title: String, client: String, time: String, status: String) {
    Card(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp),
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = Color(0xFFEDF8FF))
    ) {
        Row(modifier = Modifier.padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
            Surface(modifier = Modifier.size(50.dp), shape = RoundedCornerShape(12.dp), color = Color.White) {
                Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
                    Text(text = "OCT", fontSize = 9.sp, fontWeight = FontWeight.Bold, color = Color(0xFF991B1B))
                    Text(text = day, fontSize = 18.sp, fontWeight = FontWeight.Black, color = Color(0xFF0F172A))
                }
            }
            Spacer(modifier = Modifier.width(12.dp))
            Column(modifier = Modifier.weight(1f)) {
                Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    Text(text = title, fontWeight = FontWeight.Bold, fontSize = 14.sp, color = Color(0xFF1E293B))
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Default.AccessTime, contentDescription = null, modifier = Modifier.size(12.dp), tint = Color.Gray)
                        Text(text = " $time", fontSize = 10.sp, color = Color.Gray, fontWeight = FontWeight.Bold)
                    }
                }
                Text(text = client, fontSize = 12.sp, color = Color.Gray)
                Spacer(modifier = Modifier.height(8.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Row {
                        Box(modifier = Modifier.size(20.dp).clip(CircleShape).background(Color.Gray))
                        Box(modifier = Modifier.size(20.dp).offset(x = (-8).dp).clip(CircleShape).background(MiRed))
                    }
                    Spacer(modifier = Modifier.weight(1f))
                    Surface(color = Color(0xFFFFEDEB), shape = RoundedCornerShape(12.dp)) {
                        Text(text = status, modifier = Modifier.padding(horizontal = 10.dp, vertical = 4.dp), fontSize = 9.sp, fontWeight = FontWeight.Bold, color = Color(0xFF991B1B))
                    }
                }
            }
        }
    }
}

@Composable
fun MiBottomNavigation(
    navController: NavController,
    token: String,
    pendingApprovals: Int = 0
) {
    Surface(color = Color.White, shadowElevation = 8.dp) {
        Row(
            // Every item gets an equal slice of the bar. The old SpaceAround
            // layout let "APPROVALS" size to its text, which pushed the label
            // onto a second line and out of the bar.
            modifier = Modifier
                .fillMaxWidth()
                .navigationBarsPadding()
                .height(64.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            MiBottomNavItem(Icons.Default.GridView, "Dashboard", true, Modifier.weight(1f)) { }
            MiBottomNavItem(Icons.Default.Group, "Customers", false, Modifier.weight(1f)) {
                navController.navigate(Screen.CustomerList.createRoute(token))
            }
            MiBottomNavItem(Icons.Default.Description, "Proposals", false, Modifier.weight(1f)) {
                navController.navigate(Screen.SalesProposal.createRoute(token))
            }
            MiBottomNavItem(Icons.Default.FilterList, "Funnel", false, Modifier.weight(1f)) {
                navController.navigate(Screen.SalesFunnel.createRoute(token))
            }
            MiBottomNavItem(
                Icons.Default.FactCheck,
                "Approvals",
                false,
                Modifier.weight(1f),
                badgeCount = pendingApprovals
            ) {
                navController.navigate(Screen.PendingProposalApprovals.createRoute(token))
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MiBottomNavItem(
    icon: ImageVector,
    label: String,
    selected: Boolean,
    modifier: Modifier = Modifier,
    badgeCount: Int = 0,
    onClick: () -> Unit
) {
    val tint = if (selected) Color(0xFF991B1B) else Color(0xFF64748B)
    Column(
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
        modifier = modifier
            .fillMaxHeight()
            .clickable(onClick = onClick)
            .padding(vertical = 8.dp)
    ) {
        // The selected pill wraps the icon only (Material 3 style), so the
        // indicator width no longer depends on how long the label is.
        Box(
            modifier = Modifier
                .clip(RoundedCornerShape(50))
                .then(if (selected) Modifier.background(Color(0xFFD9EFFF)) else Modifier)
                .padding(horizontal = 16.dp, vertical = 3.dp)
        ) {
            BadgedBox(
                badge = {
                    if (badgeCount > 0) {
                        Badge(containerColor = MiRed, contentColor = Color.White) {
                            Text(if (badgeCount > 9) "9+" else badgeCount.toString(), fontSize = 9.sp)
                        }
                    }
                }
            ) {
                Icon(
                    imageVector = icon,
                    contentDescription = label,
                    tint = tint,
                    modifier = Modifier.size(22.dp)
                )
            }
        }
        Spacer(modifier = Modifier.height(3.dp))
        Text(
            text = label,
            fontSize = 10.sp,
            lineHeight = 11.sp,
            fontWeight = if (selected) FontWeight.Bold else FontWeight.Medium,
            color = tint,
            maxLines = 1,
            softWrap = false,
            textAlign = TextAlign.Center
        )
    }
}

private fun formatAmount(amount: Double): String {
    return if (amount >= 1_000_000) {
        String.format("%.1fM", amount / 1_000_000)
    } else if (amount >= 1_000) {
        String.format("%.0fK", amount / 1_000)
    } else {
        String.format("%,.0f", amount)
    }
}

@Composable
fun KpiTile(label: String, value: String, modifier: Modifier = Modifier) {
    Card(
        modifier = modifier,
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(containerColor = Color.White)
    ) {
        Column(modifier = Modifier.padding(12.dp)) {
            Text(value, fontSize = 22.sp, fontWeight = FontWeight.Black, color = Color(0xFF0F172A))
            Text(
                label.uppercase(),
                fontSize = 9.sp,
                fontWeight = FontWeight.Bold,
                color = Color(0xFF64748B),
                letterSpacing = 0.5.sp
            )
        }
    }
}

@Composable
fun FunnelStageCard(stage: FunnelStage) {
    val accent = when (stage.stage) {
        "quoted" -> Color(0xFFFCE7F3)
        "closable" -> Color(0xFFFEF9C3)
        "project" -> Color(0xFFDCFCE7)
        else -> Color(0xFFD9EFFF)
    }
    Card(
        modifier = Modifier.width(220.dp).fillMaxHeight(),
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = accent)
    ) {
        Column(
            modifier = Modifier.padding(16.dp).fillMaxSize(),
            verticalArrangement = Arrangement.SpaceBetween
        ) {
            Text(
                stage.label.uppercase(),
                fontSize = 11.sp,
                fontWeight = FontWeight.Bold,
                color = Color(0xFF475569),
                letterSpacing = 0.5.sp
            )
            Text(
                formatCompactAmount(stage.value),
                fontSize = 28.sp,
                fontWeight = FontWeight.Black,
                color = Color(0xFF0F172A)
            )
            Text(
                "${stage.count} ${if (stage.count == 1) "deal" else "deals"}",
                fontSize = 13.sp,
                color = Color(0xFF475569)
            )
        }
    }
}

/** 1_250_000 -> "₱1.3M". Keeps the funnel tiles readable at a glance. */
private fun formatCompactAmount(amount: Double): String = when {
    amount >= 1_000_000 -> "₱%.1fM".format(amount / 1_000_000)
    amount >= 1_000 -> "₱%.0fK".format(amount / 1_000)
    else -> "₱%.0f".format(amount)
}
