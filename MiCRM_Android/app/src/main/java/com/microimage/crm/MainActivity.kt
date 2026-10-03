package com.microimage.crm

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.ui.Modifier
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.microimage.crm.ui.Screen
import com.microimage.crm.ui.dashboard.DashboardScreen
import com.microimage.crm.ui.login.LoginScreen
import com.microimage.crm.ui.theme.MiCRMTheme
import com.microimage.crm.ui.customer.*
import com.microimage.crm.ui.proposal.*
import com.microimage.crm.ui.activity.*
import com.microimage.crm.ui.campaign.*

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MiCRMTheme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background
                ) {
                    val navController = rememberNavController()
                    NavHost(navController = navController, startDestination = Screen.Login.route) {
                        composable(Screen.Login.route) {
                            LoginScreen(onLoginSuccess = { token ->
                                navController.navigate(Screen.Dashboard.createRoute(token)) {
                                    popUpTo(Screen.Login.route) { inclusive = true }
                                }
                            })
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
