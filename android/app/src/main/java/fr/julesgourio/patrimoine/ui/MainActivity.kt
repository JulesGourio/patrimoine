package fr.julesgourio.patrimoine.ui

import android.Manifest
import android.os.Build
import android.os.Bundle
import android.os.SystemClock
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.biometric.BiometricManager
import androidx.biometric.BiometricManager.Authenticators.BIOMETRIC_WEAK
import androidx.biometric.BiometricManager.Authenticators.DEVICE_CREDENTIAL
import androidx.biometric.BiometricPrompt
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material.icons.automirrored.outlined.ShowChart
import androidx.compose.material.icons.automirrored.outlined.TrendingUp
import androidx.compose.material.icons.outlined.PieChart
import androidx.compose.material.icons.outlined.SwapVert
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp
import fr.julesgourio.patrimoine.ui.theme.Pt
import androidx.compose.material3.Button
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.fragment.app.FragmentActivity
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavDestination.Companion.hierarchy
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import androidx.work.WorkInfo
import androidx.work.WorkManager
import fr.julesgourio.patrimoine.ui.components.LocalRefresh
import fr.julesgourio.patrimoine.ui.components.LocalSync
import fr.julesgourio.patrimoine.ui.components.SyncControl
import fr.julesgourio.patrimoine.ui.screens.AccueilScreen
import fr.julesgourio.patrimoine.ui.screens.AjouterScreen
import fr.julesgourio.patrimoine.ui.screens.AlertesScreen
import fr.julesgourio.patrimoine.ui.screens.AnalyseScreen
import fr.julesgourio.patrimoine.ui.screens.AnalysesScreen
import fr.julesgourio.patrimoine.ui.screens.CartesScreen
import fr.julesgourio.patrimoine.ui.screens.CmbConsentScreen
import fr.julesgourio.patrimoine.ui.screens.DepensesScreen
import fr.julesgourio.patrimoine.ui.screens.OperationsScreen
import fr.julesgourio.patrimoine.ui.screens.OrdresScreen
import fr.julesgourio.patrimoine.ui.screens.ProjectionScreen
import fr.julesgourio.patrimoine.ui.screens.PlusScreen
import fr.julesgourio.patrimoine.ui.screens.PortefeuilleScreen
import fr.julesgourio.patrimoine.ui.screens.ReglagesScreen
import fr.julesgourio.patrimoine.ui.screens.TitreScreen
import fr.julesgourio.patrimoine.ui.screens.VendeursScreen
import fr.julesgourio.patrimoine.ui.theme.PatrimoineTheme
import fr.julesgourio.patrimoine.work.Scheduler
import fr.julesgourio.patrimoine.work.SyncWorker

/** FragmentActivity because the fingerprint prompt needs one. */
class MainActivity : FragmentActivity() {
    private var unlocked by mutableStateOf(false)
    private var leftAt = 0L
    private var prompting = false
    private var cancelled = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            PatrimoineTheme {
                Surface(Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
                    if (unlocked) App() else Locked(onUnlock = { cancelled = false; unlock() })
                }
            }
        }
    }

    override fun onResume() {
        super.onResume()
        // Locked again after five minutes away.
        if (unlocked && leftAt > 0 && SystemClock.elapsedRealtime() - leftAt > LOCK_AFTER_MS) unlocked = false
        if (!unlocked && !prompting && !cancelled) unlock()
    }

    override fun onStop() {
        super.onStop()
        cancelled = false // back from another app: ask again
    }

    override fun onPause() {
        super.onPause()
        leftAt = SystemClock.elapsedRealtime()
    }

    private fun unlock() {
        if (prompting) return
        val allowed = BIOMETRIC_WEAK or DEVICE_CREDENTIAL
        if (BiometricManager.from(this).canAuthenticate(allowed) != BiometricManager.BIOMETRIC_SUCCESS) {
            unlocked = true // no screen lock on the phone: nothing to check against
            return
        }
        val prompt = BiometricPrompt(this, ContextCompat.getMainExecutor(this),
            object : BiometricPrompt.AuthenticationCallback() {
                override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult) {
                    prompting = false
                    unlocked = true
                }

                override fun onAuthenticationError(errorCode: Int, errString: CharSequence) {
                    prompting = false // cancelled: the lock screen stays, with its button
                    cancelled = true
                }
            })
        prompting = true
        prompt.authenticate(
            BiometricPrompt.PromptInfo.Builder()
                .setTitle("Patrimoine")
                .setSubtitle("Déverrouille pour voir tes comptes")
                .setAllowedAuthenticators(allowed)
                .build(),
        )
    }

    private companion object {
        const val LOCK_AFTER_MS = 5 * 60 * 1000L
    }
}

@Composable
private fun Locked(onUnlock: () -> Unit) {
    Column(
        Modifier.fillMaxSize().padding(32.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp, Alignment.CenterVertically),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Icon(Icons.Filled.Lock, contentDescription = null)
        Text("Patrimoine est verrouillé", style = MaterialTheme.typography.titleMedium)
        Button(onClick = onUnlock) { Text("Déverrouiller") }
    }
}

private data class Tab(val route: String, val label: String, val icon: ImageVector)

private val TABS = listOf(
    Tab(Routes.ACCUEIL, "Patrimoine", Icons.Outlined.PieChart),
    Tab(Routes.BOURSE, "Bourse", Icons.AutoMirrored.Outlined.TrendingUp),
    Tab(Routes.DEPENSES, "Flux", Icons.Outlined.SwapVert),
    Tab(Routes.PROJECTION, "Projection", Icons.AutoMirrored.Outlined.ShowChart),
)

@Composable
private fun App() {
    val context = LocalContext.current
    val nav = rememberNavController()

    // Ask once for the notification permission (Android 13+): alerts and the Trade Republic confirmation use it.
    val askNotifications = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) {}
    LaunchedEffect(Unit) {
        if (Build.VERSION.SDK_INT >= 33 &&
            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS)
            != android.content.pm.PackageManager.PERMISSION_GRANTED
        ) askNotifications.launch(Manifest.permission.POST_NOTIFICATIONS)
    }

    // Sync: the button's one-off job and the daily one; every screen reloads when either finishes.
    val wm = remember { WorkManager.getInstance(context) }
    val now by wm.getWorkInfosForUniqueWorkFlow(Scheduler.NOW).collectAsStateWithLifecycle(emptyList())
    val daily by wm.getWorkInfosForUniqueWorkFlow(Scheduler.DAILY).collectAsStateWithLifecycle(emptyList())
    val running = (now + daily).any { it.state == WorkInfo.State.RUNNING }
    val last = now.firstOrNull { it.state.isFinished }
    var refresh by remember { mutableIntStateOf(0) }
    var wasRunning by remember { mutableStateOf(false) }
    LaunchedEffect(running) {
        if (wasRunning && !running) refresh++
        wasRunning = running
    }
    val sync = SyncControl(
        running = running,
        lastLines = last?.outputData?.getString(SyncWorker.KEY_LINES),
        lastError = last?.outputData?.getString(SyncWorker.KEY_ERROR),
        start = { Scheduler.syncNow(context) },
    )

    AppContent(nav, refresh, sync)
}

/** Tabs and screens, without WorkManager or permissions: what the screen captures render (`app/src/test`). */
@Composable
internal fun AppContent(nav: NavHostController, refresh: Int, sync: SyncControl) {
    CompositionLocalProvider(LocalRefresh provides refresh, LocalSync provides sync) {
        Scaffold(
            bottomBar = { BottomBar(nav) },
        ) { padding ->
            Column(Modifier.fillMaxSize().padding(bottom = padding.calculateBottomPadding())) {
                if (sync.running) LinearProgressIndicator(Modifier.fillMaxWidth())
                Graph(nav, Modifier.weight(1f))
            }
        }
    }
}

@Composable
private fun BottomBar(nav: NavHostController) {
    val entry by nav.currentBackStackEntryAsState()
    Column {
        HorizontalDivider(color = Pt.Ligne)
        NavigationBar(containerColor = Pt.Carte, tonalElevation = 0.dp) {
            TABS.forEach { tab ->
                val selected = entry?.destination?.hierarchy?.any { it.route == tab.route } == true
                NavigationBarItem(
                    selected = selected,
                    onClick = {
                        // Tapping the tab you are on closes the detail screens above it (restoreState would bring them back).
                        if (selected) {
                            nav.popBackStack(tab.route, inclusive = false)
                            return@NavigationBarItem
                        }
                        nav.navigate(tab.route) {
                            popUpTo(nav.graph.findStartDestination().id) { saveState = true }
                            launchSingleTop = true
                            restoreState = true
                        }
                    },
                    icon = { Icon(tab.icon, contentDescription = null) },
                    label = { Text(tab.label, maxLines = 1, fontSize = 11.sp, fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Medium) },
                    colors = NavigationBarItemDefaults.colors(
                        selectedIconColor = Pt.Encre, selectedTextColor = Pt.Encre, indicatorColor = Color.Transparent,
                        unselectedIconColor = Pt.Mute, unselectedTextColor = Pt.Mute,
                    ),
                )
            }
        }
    }
}

@Composable
private fun Graph(nav: NavHostController, modifier: Modifier) {
    val back: () -> Unit = { nav.popBackStack() }
    NavHost(nav, startDestination = Routes.ACCUEIL, modifier = modifier) {
        composable(Routes.ACCUEIL) { AccueilScreen(nav) }
        composable(Routes.BOURSE) { PortefeuilleScreen(nav) }
        composable(Routes.DEPENSES) { DepensesScreen(nav) }
        composable(Routes.ANALYSES) { AnalysesScreen(nav, back) }
        composable(Routes.PLUS) { PlusScreen(nav) }
        composable(Routes.TITRE, arguments = listOf(navArgument("symbole") { type = NavType.StringType })) {
            TitreScreen(it.arguments?.getString("symbole").orEmpty(), back)
        }
        composable(Routes.ANALYSE, arguments = listOf(navArgument("id") { type = NavType.IntType })) {
            AnalyseScreen(it.arguments?.getInt("id") ?: 0, nav, back)
        }
        composable(Routes.OPERATIONS) { OperationsScreen(back) }
        composable(Routes.VENDEURS) { VendeursScreen(back) }
        composable(Routes.CARTES) { CartesScreen(back) }
        composable(Routes.PROJECTION) { ProjectionScreen() }
        composable(Routes.AJOUTER) { AjouterScreen(back) }
        composable(Routes.ORDRES) { OrdresScreen(back) }
        composable(Routes.ALERTES) { AlertesScreen(back) }
        composable(Routes.REGLAGES) { ReglagesScreen(nav, back) }
        composable(Routes.CMB) { CmbConsentScreen(back) }
    }
}
