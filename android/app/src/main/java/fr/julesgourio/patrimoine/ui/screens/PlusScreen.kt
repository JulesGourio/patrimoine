package fr.julesgourio.patrimoine.ui.screens

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Groups
import androidx.compose.material.icons.filled.NotificationsActive
import androidx.compose.material.icons.automirrored.filled.ReceiptLong
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.SwapHoriz
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.ListItem
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.unit.dp
import androidx.navigation.NavController
import fr.julesgourio.patrimoine.ui.Routes
import fr.julesgourio.patrimoine.ui.components.ScreenScaffold

@Composable
fun PlusScreen(nav: NavController) {
    ScreenScaffold("Plus") { padding ->
        Column(Modifier.fillMaxSize().padding(padding).padding(vertical = 8.dp),
            verticalArrangement = Arrangement.spacedBy(0.dp)) {
            Entry(Icons.Filled.Groups, "Investisseurs", "Nouveautés, radar, fonds 13F, élus") { nav.navigate(Routes.INVESTISSEURS) }
            Entry(Icons.Filled.SwapHoriz, "Ordres préparés", "À passer toi-même dans Trade Republic") { nav.navigate(Routes.ORDRES) }
            Entry(Icons.Filled.NotificationsActive, "Alertes", "Règles et alertes déclenchées") { nav.navigate(Routes.ALERTES) }
            Entry(Icons.AutoMirrored.Filled.ReceiptLong, "Opérations", "Recherche, recatégorisation") { nav.navigate(Routes.OPERATIONS) }
            HorizontalDivider()
            Entry(Icons.Filled.Settings, "Réglages", "Comptes, imports, sauvegarde, notifications") { nav.navigate(Routes.REGLAGES) }
        }
    }
}

@Composable
private fun Entry(icon: ImageVector, title: String, subtitle: String, onClick: () -> Unit) {
    ListItem(
        headlineContent = { Text(title) },
        supportingContent = { Text(subtitle) },
        leadingContent = { Icon(icon, contentDescription = null) },
        modifier = Modifier.clickable(onClick = onClick),
    )
}
