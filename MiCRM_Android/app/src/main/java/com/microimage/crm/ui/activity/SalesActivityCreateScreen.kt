package com.microimage.crm.ui.activity

import android.app.DatePickerDialog
import android.widget.Toast
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.navigation.NavController
import com.microimage.crm.api.RetrofitClient
import com.microimage.crm.model.ActivityType
import com.microimage.crm.model.CustomerSummary
import com.microimage.crm.model.SalesActivityCreatePayload
import kotlinx.coroutines.launch
import java.util.*

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SalesActivityCreateScreen(token: String, navController: NavController) {
    val scope = rememberCoroutineScope()
    val context = LocalContext.current
    
    var customers by remember { mutableStateOf<List<CustomerSummary>>(emptyList()) }
    var selectedCustomer by remember { mutableStateOf<CustomerSummary?>(null) }
    var customerExpanded by remember { mutableStateOf(false) }

    var activityTypes by remember { mutableStateOf<List<ActivityType>>(emptyList()) }
    var selectedType by remember { mutableStateOf<ActivityType?>(null) }
    var typeExpanded by remember { mutableStateOf(false) }

    var title by remember { mutableStateOf("") }
    var description by remember { mutableStateOf("") }
    var scheduledDate by remember { mutableStateOf("") }

    var isSubmitting by remember { mutableStateOf(false) }

    LaunchedEffect(Unit) {
        val res = RetrofitClient.apiService.getCustomers("Token $token")
        if (res.isSuccessful) customers = res.body() ?: emptyList()

        // Activity types come from the server; this used to be hardcoded to id 1.
        val typesRes = RetrofitClient.apiService.getActivityTypes("Token $token")
        if (typesRes.isSuccessful) {
            activityTypes = typesRes.body() ?: emptyList()
            selectedType = activityTypes.firstOrNull()
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Log Activity") },
                navigationIcon = {
                    IconButton(onClick = { navController.popBackStack() }) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                    }
                }
            )
        }
    ) { padding ->
        Column(
            modifier = Modifier
                .padding(padding)
                .padding(16.dp)
                .fillMaxSize()
                .verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            OutlinedTextField(
                value = title,
                onValueChange = { title = it },
                label = { Text("Activity Title") },
                modifier = Modifier.fillMaxWidth()
            )

            ExposedDropdownMenuBox(
                expanded = customerExpanded,
                onExpandedChange = { customerExpanded = !customerExpanded }
            ) {
                OutlinedTextField(
                    value = selectedCustomer?.companyName ?: "Select Customer",
                    onValueChange = {},
                    readOnly = true,
                    label = { Text("Customer") },
                    trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = customerExpanded) },
                    modifier = Modifier.fillMaxWidth().menuAnchor()
                )
                ExposedDropdownMenu(
                    expanded = customerExpanded,
                    onDismissRequest = { customerExpanded = false }
                ) {
                    customers.forEach { customer ->
                        DropdownMenuItem(
                            text = { Text(customer.companyName) },
                            onClick = {
                                selectedCustomer = customer
                                customerExpanded = false
                            }
                        )
                    }
                }
            }

            OutlinedTextField(
                value = scheduledDate,
                onValueChange = { scheduledDate = it },
                label = { Text("Scheduled Date (YYYY-MM-DD)") },
                modifier = Modifier.fillMaxWidth(),
                placeholder = { Text("2024-12-31") }
            )

            ExposedDropdownMenuBox(
                expanded = typeExpanded,
                onExpandedChange = { typeExpanded = !typeExpanded }
            ) {
                OutlinedTextField(
                    value = selectedType?.name ?: "Select activity type",
                    onValueChange = {},
                    readOnly = true,
                    label = { Text("Activity Type") },
                    trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = typeExpanded) },
                    modifier = Modifier.menuAnchor().fillMaxWidth()
                )
                ExposedDropdownMenu(
                    expanded = typeExpanded,
                    onDismissRequest = { typeExpanded = false }
                ) {
                    activityTypes.forEach { type ->
                        DropdownMenuItem(
                            text = { Text(type.name) },
                            onClick = {
                                selectedType = type
                                typeExpanded = false
                            }
                        )
                    }
                }
            }

            OutlinedTextField(
                value = description,
                onValueChange = { description = it },
                label = { Text("Description/Notes") },
                modifier = Modifier.fillMaxWidth(),
                minLines = 3
            )

            Button(
                onClick = {
                    if (title.isBlank()) {
                        Toast.makeText(context, "Title is required", Toast.LENGTH_SHORT).show()
                        return@Button
                    }
                    val typeId = selectedType?.id
                    if (typeId == null) {
                        Toast.makeText(context, "Select an activity type", Toast.LENGTH_SHORT).show()
                        return@Button
                    }
                    isSubmitting = true
                    scope.launch {
                        try {
                            val payload = SalesActivityCreatePayload(
                                title = title,
                                description = description,
                                customer = selectedCustomer?.id,
                                scheduledStart = scheduledDate.takeIf { it.isNotBlank() },
                                activityType = typeId
                            )
                            val res = RetrofitClient.apiService.createSalesActivity("Token $token", payload)
                            if (res.isSuccessful) {
                                Toast.makeText(context, "Activity Logged", Toast.LENGTH_SHORT).show()
                                navController.popBackStack()
                            } else {
                                Toast.makeText(
                                    context,
                                    "Could not save activity (${res.code()})",
                                    Toast.LENGTH_LONG
                                ).show()
                            }
                        } catch (e: Exception) {
                            Toast.makeText(context, "Error: ${e.message}", Toast.LENGTH_SHORT).show()
                        } finally {
                            isSubmitting = false
                        }
                    }
                },
                modifier = Modifier.fillMaxWidth().height(56.dp),
                enabled = !isSubmitting
            ) {
                if (isSubmitting) CircularProgressIndicator(color = androidx.compose.ui.graphics.Color.White)
                else Text("Save Activity")
            }
        }
    }
}
