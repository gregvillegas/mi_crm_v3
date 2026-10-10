package com.microimage.crm.ui.login

import android.widget.Toast
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.fragment.app.FragmentActivity
import com.microimage.crm.api.RetrofitClient
import com.microimage.crm.auth.BiometricAuth
import com.microimage.crm.auth.SessionStore
import com.microimage.crm.model.LoginRequest
import com.microimage.crm.model.MfaVerifyRequest
import com.microimage.crm.ui.theme.MiBgGradientEnd
import com.microimage.crm.ui.theme.MiBgGradientStart
import com.microimage.crm.ui.theme.MiRed
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun LoginScreen(
    activity: FragmentActivity,
    sessionStore: SessionStore,
    onLoginSuccess: (String) -> Unit,
) {
    var username by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var serverAddress by remember { mutableStateOf(RetrofitClient.DEFAULT_HOST) }
    var passwordVisible by remember { mutableStateOf(false) }
    var keepSignedIn by remember { mutableStateOf(false) }
    var isLoading by remember { mutableStateOf(false) }
    var showServerSettings by remember { mutableStateOf(false) }

    // Second-factor step. Non-null mfaToken means the password was accepted and
    // the server is waiting for an authenticator code.
    var mfaToken by remember { mutableStateOf<String?>(null) }
    var mfaCode by remember { mutableStateOf("") }
    var mfaError by remember { mutableStateOf<String?>(null) }
    var isVerifying by remember { mutableStateOf(false) }

    // When a login succeeds and the device supports biometrics, offer to enable
    // biometric unlock before proceeding to the dashboard.
    var pendingToken by remember { mutableStateOf<String?>(null) }

    val scope = rememberCoroutineScope()
    val context = LocalContext.current

    // Called with a fresh token from either the direct or the MFA path. Offers
    // the biometric opt-in if the hardware supports it; otherwise proceeds.
    fun handleToken(token: String) {
        if (BiometricAuth.canAuthenticate(activity)) {
            pendingToken = token
        } else {
            onLoginSuccess(token)
        }
    }

    pendingToken?.let { token ->
        AlertDialog(
            onDismissRequest = { },
            icon = { Icon(Icons.Default.Fingerprint, contentDescription = null, tint = MiRed) },
            title = { Text("Enable biometric login?", fontWeight = FontWeight.Bold) },
            text = {
                Text(
                    "Next time, unlock MiCRM with your fingerprint, face, or screen lock — " +
                        "no password or code needed on this device.",
                    fontSize = 14.sp,
                    color = Color.Gray
                )
            },
            confirmButton = {
                Button(
                    onClick = {
                        sessionStore.saveSession(token, username.trim(), serverAddress.trim())
                        pendingToken = null
                        onLoginSuccess(token)
                    },
                    colors = ButtonDefaults.buttonColors(containerColor = MiRed)
                ) { Text("Enable") }
            },
            dismissButton = {
                TextButton(onClick = {
                    // User declined — make sure no stale session lingers.
                    sessionStore.clear()
                    pendingToken = null
                    onLoginSuccess(token)
                }) { Text("Not now") }
            }
        )
    }

    mfaToken?.let { pendingToken ->
        MfaCodeDialog(
            code = mfaCode,
            onCodeChange = { mfaCode = it.filter(Char::isDigit).take(8); mfaError = null },
            errorMessage = mfaError,
            isVerifying = isVerifying,
            onDismiss = { mfaToken = null; mfaCode = ""; mfaError = null },
            onSubmit = {
                isVerifying = true
                scope.launch {
                    try {
                        val response = RetrofitClient.apiService.verifyMfa(
                            MfaVerifyRequest(pendingToken, mfaCode)
                        )
                        val token = response.body()?.token
                        if (response.isSuccessful && token != null) {
                            mfaToken = null
                            handleToken(token)
                        } else {
                            mfaError = response.body()?.detail
                                ?: "That code is not valid. Please try again."
                        }
                    } catch (e: Exception) {
                        mfaError = "Connection error: ${e.message}"
                    } finally {
                        isVerifying = false
                    }
                }
            }
        )
    }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(
                Brush.verticalGradient(
                    colors = listOf(MiBgGradientStart, MiBgGradientEnd)
                )
            )
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(24.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Spacer(modifier = Modifier.height(40.dp))

            // Logo Header
            Row(verticalAlignment = Alignment.CenterVertically) {
                Surface(
                    color = MiRed,
                    shape = RoundedCornerShape(8.dp),
                    modifier = Modifier.size(48.dp)
                ) {
                    Box(contentAlignment = Alignment.Center) {
                        Text("M", color = Color.White, fontWeight = FontWeight.Bold, fontSize = 24.sp)
                    }
                }
                Spacer(modifier = Modifier.width(12.dp))
                Text(
                    text = "MiCRM",
                    style = MaterialTheme.typography.headlineLarge,
                    fontWeight = FontWeight.Bold,
                    color = MiRed,
                    letterSpacing = 1.sp
                )
            }

            Spacer(modifier = Modifier.height(16.dp))
            Text(
                "Micro Image International Corp.",
                fontWeight = FontWeight.Bold,
                fontSize = 18.sp,
                color = Color.Black
            )
            
            IconButton(onClick = { showServerSettings = !showServerSettings }) {
                Icon(
                    imageVector = Icons.Default.Settings,
                    contentDescription = "Server Settings",
                    tint = if (showServerSettings) MiRed else Color.Gray
                )
            }

            if (showServerSettings) {
                Card(
                    modifier = Modifier.fillMaxWidth().padding(vertical = 8.dp),
                    colors = CardDefaults.cardColors(containerColor = Color(0xFFFFF3E0)),
                    shape = RoundedCornerShape(8.dp)
                ) {
                    Column(modifier = Modifier.padding(16.dp)) {
                        Text("SERVER CONFIGURATION", style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.Bold)
                        Spacer(modifier = Modifier.height(8.dp))
                        TextField(
                            value = serverAddress,
                            onValueChange = { serverAddress = it },
                            placeholder = { Text("e.g. micrm.microimageph.com") },
                            leadingIcon = { Icon(Icons.Default.Dns, contentDescription = null) },
                            modifier = Modifier.fillMaxWidth(),
                            singleLine = true,
                            colors = TextFieldDefaults.colors(
                                focusedContainerColor = Color.White,
                                unfocusedContainerColor = Color.White
                            )
                        )
                        Text("Current: $serverAddress", fontSize = 10.sp, color = Color.Gray)
                    }
                }
            } else {
                Text(
                    "Authorized personnel only",
                    fontSize = 14.sp,
                    color = Color.Gray
                )
            }

            Spacer(modifier = Modifier.height(24.dp))

            // Login Card
            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(containerColor = Color.White),
                elevation = CardDefaults.cardElevation(defaultElevation = 4.dp),
                shape = RoundedCornerShape(12.dp)
            ) {
                Column(modifier = Modifier.padding(24.dp)) {
                    Text("USERNAME", style = MaterialTheme.typography.labelLarge, color = Color(0xFF795548))
                    Spacer(modifier = Modifier.height(8.dp))
                    TextField(
                        value = username,
                        onValueChange = { username = it },
                        placeholder = { Text("Enter your ID") },
                        leadingIcon = { Icon(Icons.Default.Person, contentDescription = null, tint = Color(0xFF795548)) },
                        modifier = Modifier.fillMaxWidth(),
                        colors = TextFieldDefaults.colors(
                            focusedContainerColor = Color(0xFFE1F5FE),
                            unfocusedContainerColor = Color(0xFFE1F5FE),
                            focusedIndicatorColor = Color.Transparent,
                            unfocusedIndicatorColor = Color.Transparent
                        ),
                        shape = RoundedCornerShape(8.dp)
                    )

                    Spacer(modifier = Modifier.height(24.dp))

                    Text("PASSWORD", style = MaterialTheme.typography.labelLarge, color = Color(0xFF795548))
                    Spacer(modifier = Modifier.height(8.dp))
                    TextField(
                        value = password,
                        onValueChange = { password = it },
                        placeholder = { Text("••••••••") },
                        leadingIcon = { Icon(Icons.Default.Lock, contentDescription = null, tint = Color(0xFF795548)) },
                        trailingIcon = {
                            IconButton(onClick = { passwordVisible = !passwordVisible }) {
                                Icon(
                                    if (passwordVisible) Icons.Default.Visibility else Icons.Default.VisibilityOff,
                                    contentDescription = null,
                                    tint = Color(0xFF795548)
                                )
                            }
                        },
                        visualTransformation = if (passwordVisible) VisualTransformation.None else PasswordVisualTransformation(),
                        modifier = Modifier.fillMaxWidth(),
                        colors = TextFieldDefaults.colors(
                            focusedContainerColor = Color(0xFFE1F5FE),
                            unfocusedContainerColor = Color(0xFFE1F5FE),
                            focusedIndicatorColor = Color.Transparent,
                            unfocusedIndicatorColor = Color.Transparent
                        ),
                        shape = RoundedCornerShape(8.dp)
                    )

                    Spacer(modifier = Modifier.height(16.dp))

                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(checked = keepSignedIn, onCheckedChange = { keepSignedIn = it })
                        Text("Keep me signed in", fontSize = 14.sp, color = Color.Gray)
                    }

                    Spacer(modifier = Modifier.height(16.dp))

                    Button(
                        onClick = {
                            isLoading = true
                            RetrofitClient.updateBaseUrl(serverAddress)
                            scope.launch {
                                try {
                                    val response = RetrofitClient.apiService.login(LoginRequest(username, password))
                                    val body = response.body()
                                    when {
                                        // Account has MFA — ask for the authenticator code.
                                        response.isSuccessful && body?.mfaRequired == true && body.mfaToken != null -> {
                                            mfaToken = body.mfaToken
                                            mfaCode = ""
                                            mfaError = null
                                        }
                                        response.isSuccessful && body?.token != null -> {
                                            handleToken(body.token)
                                        }
                                        // Site requires MFA but this account has not enrolled yet.
                                        response.code() == 403 -> {
                                            Toast.makeText(
                                                context,
                                                "Two-factor authentication must be set up on the CRM website first.",
                                                Toast.LENGTH_LONG
                                            ).show()
                                        }
                                        else -> {
                                            Toast.makeText(context, "Login Failed: ${response.code()}", Toast.LENGTH_SHORT).show()
                                        }
                                    }
                                } catch (e: Exception) {
                                    Toast.makeText(context, "Connection Error: ${e.message}", Toast.LENGTH_LONG).show()
                                } finally {
                                    isLoading = false
                                }
                            }
                        },
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(56.dp),
                        colors = ButtonDefaults.buttonColors(containerColor = MiRed),
                        shape = RoundedCornerShape(8.dp),
                        enabled = !isLoading
                    ) {
                        if (isLoading) {
                            CircularProgressIndicator(color = Color.White, modifier = Modifier.size(24.dp))
                        } else {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Text("Secure Login", fontWeight = FontWeight.Bold, fontSize = 18.sp)
                                Spacer(modifier = Modifier.width(8.dp))
                                Icon(Icons.Default.ArrowForward, contentDescription = null)
                            }
                        }
                    }

                    Spacer(modifier = Modifier.height(24.dp))
                    Text(
                        "Having trouble? Contact support",
                        modifier = Modifier.fillMaxWidth(),
                        textAlign = TextAlign.Center,
                        fontSize = 14.sp,
                        color = Color(0xFF795548),
                        fontWeight = FontWeight.Bold
                    )
                }
            }

            Spacer(modifier = Modifier.height(24.dp))

            // Bottom Buttons
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                BottomOptionButton(
                    icon = Icons.Default.VpnKey,
                    label = "PASSKEY",
                    modifier = Modifier.weight(1f)
                )
                BottomOptionButton(
                    icon = Icons.Default.Business,
                    label = "SSO LOGIN",
                    modifier = Modifier.weight(1f)
                )
            }

            Spacer(modifier = Modifier.weight(1f))

            // Footer
            Text("GLOBAL SERVERS ONLINE", fontSize = 12.sp, color = Color.Gray, letterSpacing = 1.sp)
            Text("V2.4.0-STABLE BUILD", fontSize = 12.sp, color = Color.Gray, letterSpacing = 1.sp)
            Spacer(modifier = Modifier.height(16.dp))
        }
    }
}

@Composable
fun BottomOptionButton(icon: ImageVector, label: String, modifier: Modifier = Modifier) {
    Surface(
        modifier = modifier.height(80.dp),
        color = Color(0xFFE1F5FE),
        shape = RoundedCornerShape(8.dp)
    ) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center
        ) {
            Icon(icon, contentDescription = null, tint = Color(0xFF795548))
            Spacer(modifier = Modifier.height(8.dp))
            Text(label, fontSize = 10.sp, fontWeight = FontWeight.Bold, color = Color(0xFF795548))
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun MfaCodeDialog(
    code: String,
    onCodeChange: (String) -> Unit,
    errorMessage: String?,
    isVerifying: Boolean,
    onDismiss: () -> Unit,
    onSubmit: () -> Unit
) {
    AlertDialog(
        onDismissRequest = { if (!isVerifying) onDismiss() },
        icon = { Icon(Icons.Default.Shield, contentDescription = null, tint = MiRed) },
        title = { Text("Two-Factor Authentication", fontWeight = FontWeight.Bold) },
        text = {
            Column {
                Text(
                    "Enter the 6-digit code from your authenticator app. " +
                        "You can also use one of your recovery codes.",
                    fontSize = 14.sp,
                    color = Color.Gray
                )
                Spacer(modifier = Modifier.height(16.dp))
                OutlinedTextField(
                    value = code,
                    onValueChange = onCodeChange,
                    label = { Text("Authentication code") },
                    singleLine = true,
                    isError = errorMessage != null,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword),
                    modifier = Modifier.fillMaxWidth()
                )
                if (errorMessage != null) {
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(errorMessage, color = MaterialTheme.colorScheme.error, fontSize = 13.sp)
                }
            }
        },
        confirmButton = {
            Button(
                onClick = onSubmit,
                enabled = !isVerifying && code.length >= 6,
                colors = ButtonDefaults.buttonColors(containerColor = MiRed)
            ) {
                if (isVerifying) {
                    CircularProgressIndicator(color = Color.White, modifier = Modifier.size(18.dp))
                } else {
                    Text("Verify")
                }
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss, enabled = !isVerifying) { Text("Cancel") }
        }
    )
}
