package com.microimage.crm

import android.os.Bundle
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.fragment.app.FragmentActivity
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.microimage.crm.api.RetrofitClient
import com.microimage.crm.auth.SessionStore
import com.microimage.crm.ui.Screen
import com.microimage.crm.ui.dashboard.DashboardScreen
import com.microimage.crm.ui.login.LoginScreen
import com.microimage.crm.ui.login.UnlockScreen
import com.microimage.crm.ui.theme.MiCRMTheme
import com.microimage.crm.ui.customer.*
import com.microimage.crm.ui.proposal.*
import com.microimage.crm.ui.activity.*
import com.microimage.crm.ui.campaign.*

// FragmentActivity (not ComponentActivity) is required to host AndroidX
// BiometricPrompt. FragmentActivity extends ComponentActivity, so Compose and
// everything else continue to work unchanged.
class MainActivity : FragmentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MiCRMTheme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background
                ) {
                    val activity = this
                    val context = LocalContext.current
                    val sessionStore = remember { SessionStore(context) }
                    val navController = rememberNavController()

                    // Start on the Unlock screen. It decides whether to show the
                    // biometric prompt (remembered session) or jump to Login.
                    NavHost(navController = navController, startDestination = Screen.Unlock.route) {
                        composable(Screen.Unlock.route) {
                            UnlockScreen(
                                activity = activity,
                                sessionStore = sessionStore,
                                onUnlocked = { token ->
                                    // Point the API client at the host this session belongs to.
                                    sessionStore.serverHost?.let { RetrofitClient.updateBaseUrl(it) }
                                    navController.navigate(Screen.Dashboard.createRoute(token)) {
                                        popUpTo(Screen.Unlock.route) { inclusive = true }
                                    }
                                },
                                onUsePassword = {
                                    navController.navigate(Screen.Login.route) {
                                        popUpTo(Screen.Unlock.route) { inclusive = true }
                                    }
                                }
                            )
                        }
                        composable(Screen.Login.route) {
                            LoginScreen(
                                activity = activity,
                                sessionStore = sessionStore,
                                onLoginSuccess = { token ->
                                    navController.navigate(Screen.Dashboard.createRoute(token)) {
                                        popUpTo(Screen.Login.route) { inclusive = true }
                                    }
                                }
                            )
                        }
                        composable(
                            route = Screen.Dashboard.route,
                            arguments = listOf(navArgument("token") { type = NavType.StringType })
                        ) { backStackEntry ->
                            val token = backStackEntry.arguments?.getString("token") ?: ""
                            DashboardScreen(token = token, navController = navController)
                        }

                        // --- CUSTOMERS ---
                        composable(
                            route = Screen.CustomerList.route,
                            arguments = listOf(navArgument("token") { type = NavType.StringType })
                        ) { backStackEntry ->
                            val token = backStackEntry.arguments?.getString("token") ?: ""
                            CustomerListScreen(token, navController)
                        }
                        composable(
                            route = Screen.CustomerDetail.route,
                            arguments = listOf(
                                navArgument("token") { type = NavType.StringType },
                                navArgument("id") { type = NavType.IntType }
                            )
                        ) { backStackEntry ->
                            val token = backStackEntry.arguments?.getString("token") ?: ""
                            val id = backStackEntry.arguments?.getInt("id") ?: 0
                            CustomerDetailScreen(token, id, navController)
                        }
                        composable(
                            route = Screen.CustomerCreateRequest.route,
                            arguments = listOf(navArgument("token") { type = NavType.StringType })
                        ) { backStackEntry ->
                            val token = backStackEntry.arguments?.getString("token") ?: ""
                            CustomerCreateRequestScreen(token, navController)
                        }
                        composable(
                            route = Screen.MyCustomerRequests.route,
                            arguments = listOf(navArgument("token") { type = NavType.StringType })
                        ) { backStackEntry ->
                            val token = backStackEntry.arguments?.getString("token") ?: ""
                            MyCustomerRequestsScreen(token, navController)
                        }
                        composable(
                            route = Screen.PendingCustomerRequests.route,
                            arguments = listOf(navArgument("token") { type = NavType.StringType })
                        ) { backStackEntry ->
                            val token = backStackEntry.arguments?.getString("token") ?: ""
                            PendingCustomerRequestsScreen(token, navController)
                        }

                        // --- PROPOSALS ---
                        composable(
                            route = Screen.SalesProposal.route,
                            arguments = listOf(navArgument("token") { type = NavType.StringType })
                        ) { backStackEntry ->
                            val token = backStackEntry.arguments?.getString("token") ?: ""
                            SalesProposalScreen(token, navController)
                        }
                        composable(
                            route = Screen.ProposalDetail.route,
                            arguments = listOf(
                                navArgument("token") { type = NavType.StringType },
                                navArgument("id") { type = NavType.IntType }
                            )
                        ) { backStackEntry ->
                            val token = backStackEntry.arguments?.getString("token") ?: ""
                            val id = backStackEntry.arguments?.getInt("id") ?: 0
                            ProposalDetailScreen(token, id, navController)
                        }
                        composable(
                            route = Screen.ProposalCreate.route,
                            arguments = listOf(navArgument("token") { type = NavType.StringType })
                        ) { backStackEntry ->
                            val token = backStackEntry.arguments?.getString("token") ?: ""
                            ProposalCreateScreen(token, navController)
                        }
                        composable(
                            route = Screen.PendingProposalApprovals.route,
                            arguments = listOf(navArgument("token") { type = NavType.StringType })
                        ) { backStackEntry ->
                            val token = backStackEntry.arguments?.getString("token") ?: ""
                            PendingProposalApprovalsScreen(token, navController)
                        }

                        // --- SALES MONITORING ---
                        composable(
                            route = Screen.SalesFunnel.route,
                            arguments = listOf(navArgument("token") { type = NavType.StringType })
                        ) { backStackEntry ->
                            val token = backStackEntry.arguments?.getString("token") ?: ""
                            com.microimage.crm.ui.funnel.SalesFunnelScreen(token, navController)
                        }
                        composable(
                            route = Screen.FunnelDetail.route,
                            arguments = listOf(
                                navArgument("token") { type = NavType.StringType },
                                navArgument("id") { type = NavType.IntType }
                            )
                        ) { backStackEntry ->
                            val token = backStackEntry.arguments?.getString("token") ?: ""
                            val id = backStackEntry.arguments?.getInt("id") ?: 0
                            com.microimage.crm.ui.funnel.FunnelDetailScreen(token, id, navController)
                        }
                        composable(
                            route = Screen.SalesActivityCreate.route,
                            arguments = listOf(navArgument("token") { type = NavType.StringType })
                        ) { backStackEntry ->
                            val token = backStackEntry.arguments?.getString("token") ?: ""
                            SalesActivityCreateScreen(token, navController)
                        }

                        // --- CAMPAIGNS ---
                        composable(
                            route = Screen.CampaignList.route,
                            arguments = listOf(navArgument("token") { type = NavType.StringType })
                        ) { backStackEntry ->
                            val token = backStackEntry.arguments?.getString("token") ?: ""
                            CampaignListScreen(token, navController)
                        }

                        composable(
                            route = Screen.Settings.route,
                            arguments = listOf(navArgument("token") { type = NavType.StringType })
                        ) { backStackEntry ->
                            val token = backStackEntry.arguments?.getString("token") ?: ""
                            com.microimage.crm.ui.settings.SettingsScreen(token, navController)
                        }

                        // --- GLOBAL SEARCH ---
                        composable(
                            route = Screen.GlobalSearch.route,
                            arguments = listOf(navArgument("token") { type = NavType.StringType })
                        ) { backStackEntry ->
                            val token = backStackEntry.arguments?.getString("token") ?: ""
                            com.microimage.crm.ui.search.GlobalSearchScreen(token, navController)
                        }
                    }
                }
            }
        }
    }
}
