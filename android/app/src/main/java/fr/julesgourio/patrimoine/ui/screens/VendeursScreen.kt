package fr.julesgourio.patrimoine.ui.screens

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.SuggestionChip
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import fr.julesgourio.patrimoine.engine.Engine
import fr.julesgourio.patrimoine.engine.Reply
import fr.julesgourio.patrimoine.ui.components.CallScreen
import fr.julesgourio.patrimoine.ui.components.Muted
import fr.julesgourio.patrimoine.ui.components.ScreenScaffold
import fr.julesgourio.patrimoine.ui.components.bool
import fr.julesgourio.patrimoine.ui.components.day
import fr.julesgourio.patrimoine.ui.components.euros
import fr.julesgourio.patrimoine.ui.components.int
import fr.julesgourio.patrimoine.ui.components.list
import fr.julesgourio.patrimoine.ui.components.num
import fr.julesgourio.patrimoine.ui.components.rememberCall
import fr.julesgourio.patrimoine.ui.components.str
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import org.json.JSONObject

/** Vendeurs : renommer, fusionner, exclure des abonnements. Les opérations ne sont pas modifiées. */
@Composable
fun VendeursScreen(onBack: () -> Unit) {
    var saisie by remember { mutableStateOf("") }
    var q by remember { mutableStateOf("") }
    var cible by remember { mutableStateOf<JSONObject?>(null) }
    var confirmation by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(saisie) {
        delay(400)
        q = saisie.trim()
    }

    val state = rememberCall("vendeurs", Engine.args("recherche" to q, "limite" to 100), q)

    ScreenScaffold("Vendeurs", onBack = onBack) { padding ->
        Column(Modifier.padding(padding)) {
            Column(
                Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                OutlinedTextField(
                    value = saisie,
                    onValueChange = { saisie = it },
                    modifier = Modifier.fillMaxWidth(),
                    label = { Text("Rechercher un vendeur") },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
                    keyboardActions = KeyboardActions(onSearch = { q = saisie.trim() }),
                )
                confirmation?.let { Text(it, color = MaterialTheme.colorScheme.primary, style = MaterialTheme.typography.bodyMedium) }
            }
            androidx.compose.foundation.layout.Box(Modifier.weight(1f)) {
                CallScreen(state) { d ->
                    val vendeurs = d.list("vendeurs")
                    if (vendeurs.isEmpty()) item { Muted("Aucun vendeur pour cette recherche.") }
                    items(vendeurs, key = { (it.str("sens") ?: "") + "|" + (it.str("brut") ?: it.hashCode().toString()) }) { v ->
                        val brut = v.str("brut") ?: "—"
                        val affiche = v.str("affiche") ?: brut
                        val revenu = v.str("sens") == "revenu"
                        val n = v.int("operations") ?: 0
                        Column(Modifier.fillMaxWidth().clickable { cible = v }) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Column(Modifier.weight(1f)) {
                                    Text(affiche, style = MaterialTheme.typography.bodyLarge, maxLines = 2)
                                    if (affiche != brut) Muted(brut)
                                    Muted(
                                        "$n opération" + (if (n > 1) "s" else "") + " · dernier " + day(v.str("dernier")) +
                                            if (revenu) " · revenu" else "",
                                    )
                                }
                                Text(euros(v.num("total")), style = MaterialTheme.typography.bodyLarge)
                            }
                            if (v.bool("pas_abonnement")) {
                                SuggestionChip(onClick = { cible = v }, label = { Text("pas un abonnement") })
                            }
                            HorizontalDivider(Modifier.padding(top = 8.dp))
                        }
                    }
                }
            }
        }
    }

    cible?.let { v ->
        RenameVendorDialog(
            raw = v.str("brut") ?: "",
            nomActuel = v.str("affiche") ?: v.str("brut") ?: "",
            pasAbonnement = v.bool("pas_abonnement"),
            onDismiss = { cible = null },
            onDone = { msg ->
                cible = null
                confirmation = msg
                state.reload()
            },
        )
    }
}

/**
 * Boîte « Renommer ce vendeur » (écran Vendeurs et détail d'une opération). [raw] est le nom brut ou le nom affiché
 * actuel ; [onDone] reçoit le message de confirmation après un succès du moteur.
 */
@Composable
fun RenameVendorDialog(
    raw: String,
    nomActuel: String,
    pasAbonnement: Boolean,
    onDismiss: () -> Unit,
    onDone: (String) -> Unit,
) {
    val scope = rememberCoroutineScope()
    var nom by remember(raw) { mutableStateOf(nomActuel) }
    var exclu by remember(raw) { mutableStateOf(pasAbonnement) }
    var erreur by remember { mutableStateOf<String?>(null) }
    var occupe by remember { mutableStateOf(false) }

    fun envoyer(nouveauNom: String, message: String) {
        occupe = true
        erreur = null
        scope.launch {
            // pas_abonnement n'est envoyé que s'il a changé (null = inchangé pour le moteur).
            val args = Engine.args(
                "raw" to raw,
                "nouveau_nom" to nouveauNom,
                "pas_abonnement" to (if (exclu != pasAbonnement) exclu else null),
            )
            when (val r = Engine.call("renommer_vendeur", args)) {
                is Reply.Ok -> {
                    val e = (r.data as? JSONObject)?.str("erreur")
                    if (e != null) {
                        erreur = e
                        occupe = false
                    } else {
                        onDone(message)
                    }
                }
                is Reply.Err -> {
                    erreur = r.message
                    occupe = false
                }
            }
        }
    }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Renommer le vendeur") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                if (raw != nomActuel) Muted(raw)
                OutlinedTextField(
                    value = nom,
                    onValueChange = { nom = it },
                    label = { Text("Nouveau nom") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                Muted("Le même nom donné à plusieurs vendeurs les fusionne.")
                Row(
                    Modifier.fillMaxWidth().clickable { exclu = !exclu },
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Checkbox(checked = exclu, onCheckedChange = { exclu = it })
                    Text("Ce n'est pas un abonnement")
                }
                erreur?.let { Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall) }
            }
        },
        confirmButton = {
            Button(
                enabled = !occupe,
                onClick = { envoyer(nom.trim(), if (nom.isBlank()) "Nom retiré." else "Vendeur renommé.") },
            ) { Text("Enregistrer") }
        },
        dismissButton = {
            Row {
                TextButton(enabled = !occupe, onClick = { envoyer("", "Nom retiré.") }) { Text("Retirer le nom") }
                TextButton(onClick = onDismiss) { Text("Annuler") }
            }
        },
    )
}
