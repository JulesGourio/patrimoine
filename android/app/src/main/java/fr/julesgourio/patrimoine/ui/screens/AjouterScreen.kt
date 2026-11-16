package fr.julesgourio.patrimoine.ui.screens

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import fr.julesgourio.patrimoine.ui.components.Muted
import fr.julesgourio.patrimoine.ui.components.ScreenScaffold

/** Écran « Ajouter » : vide pour l'instant (ajout d'un compte ou d'une position, étape suivante). */
@Composable
fun AjouterScreen(onBack: () -> Unit) {
    ScreenScaffold("Ajouter", onBack = onBack) { padding ->
        Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) { Muted("Bientôt disponible") }
    }
}
