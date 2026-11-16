package fr.julesgourio.patrimoine.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import fr.julesgourio.patrimoine.engine.Engine
import fr.julesgourio.patrimoine.engine.Reply
import fr.julesgourio.patrimoine.ui.components.CallScreen
import fr.julesgourio.patrimoine.ui.components.Muted
import fr.julesgourio.patrimoine.ui.components.ScreenScaffold
import fr.julesgourio.patrimoine.ui.components.SectionCard
import fr.julesgourio.patrimoine.ui.components.day
import fr.julesgourio.patrimoine.ui.components.gainColor
import fr.julesgourio.patrimoine.ui.theme.LocalMoney
import fr.julesgourio.patrimoine.ui.components.euros
import fr.julesgourio.patrimoine.ui.components.int
import fr.julesgourio.patrimoine.ui.components.list
import fr.julesgourio.patrimoine.ui.components.num
import fr.julesgourio.patrimoine.ui.components.rememberCall
import fr.julesgourio.patrimoine.ui.components.str
import kotlinx.coroutines.launch
import org.json.JSONObject

private enum class Action { OPERATION, SOLDE, IMPORT, NOUVELLE }

/** Titres-restaurant (et autres comptes tenus à la main) : solde, reçu et dépensé du mois, mouvements. */
@Composable
fun CartesScreen(onBack: () -> Unit) {
    val state = rememberCall("cartes")
    var action by remember { mutableStateOf<Pair<Action, JSONObject?>?>(null) }
    var message by remember { mutableStateOf<String?>(null) }

    ScreenScaffold("Titres-restaurant", onBack = onBack) { padding ->
        CallScreen(state, padding) { d ->
            val cartes = d.list("cartes")
            message?.let { item { Text(it, color = MaterialTheme.colorScheme.primary) } }
            if (cartes.isEmpty()) item { Muted("Aucun compte. Crée-en un pour suivre un solde tenu à la main.") }
            cartes.forEach { c ->
                item(key = c.str("id")) {
                    SectionCard(c.str("nom") ?: "Compte") {
                        Text("Solde", style = MaterialTheme.typography.labelLarge)
                        Text(euros(c.num("solde")), style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.SemiBold)
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(24.dp)) {
                            Column {
                                Muted("Reçu ce mois")
                                Text(euros(c.num("recu_mois"), sign = true), color = LocalMoney.current.gain,
                                    style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                            }
                            Column {
                                Muted("Dépensé ce mois")
                                Text(euros(-(c.num("depense_mois") ?: 0.0), sign = true), color = LocalMoney.current.loss,
                                    style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                            }
                        }
                        val age = c.int("jours_depuis_maj")
                        if (age != null && age > 14) Muted("Pas de saisie depuis $age jours : le solde peut être faux.")
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Button(onClick = { action = Action.OPERATION to c }) { Text("Ajouter") }
                            OutlinedButton(onClick = { action = Action.SOLDE to c }) { Text("Recaler") }
                            OutlinedButton(onClick = { action = Action.IMPORT to c }) { Text("Importer") }
                        }
                    }
                }
                item(key = c.str("id") + "-mouvements") {
                    SectionCard("Mouvements") {
                        val moves = c.list("mouvements")
                        if (moves.isEmpty()) Muted("Aucun mouvement.")
                        moves.forEachIndexed { i, m ->
                            if (i > 0) HorizontalDivider()
                            val montant = m.num("montant") ?: 0.0
                            val ajust = m.str("type") == "ajustement"
                            Row(Modifier.fillMaxWidth().padding(vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                                Column(Modifier.weight(1f)) {
                                    Text(m.str("libelle").orEmpty(), maxLines = 1, overflow = TextOverflow.Ellipsis)
                                    Muted(day(m.str("date")) + if (ajust) " · ajustement du solde" else "")
                                }
                                Text(euros(montant, sign = true),
                                    color = if (ajust) MaterialTheme.colorScheme.onSurfaceVariant else gainColor(montant),
                                    fontWeight = FontWeight.Medium)
                            }
                        }
                    }
                }
            }
            item { OutlinedButton(onClick = { action = Action.NOUVELLE to null }, modifier = Modifier.fillMaxWidth()) { Text("Nouveau compte") } }
        }
    }

    action?.let { (a, carte) ->
        CarteDialog(a, carte, onDismiss = { action = null }) { msg ->
            action = null
            message = msg
            state.reload()
        }
    }
}

/** Appelle un outil du moteur ; rend le message d'erreur (champ « erreur » ou erreur de pont) ou null si tout va bien. */
private suspend fun appeler(outil: String, args: JSONObject): Pair<String?, JSONObject?> =
    when (val r = Engine.call(outil, args)) {
        is Reply.Ok -> (r.data as? JSONObject).let { it?.str("erreur") to it }
        is Reply.Err -> r.message to null
    }

@Composable
private fun CarteDialog(action: Action, carte: JSONObject?, onDismiss: () -> Unit, onDone: (String) -> Unit) {
    val scope = rememberCoroutineScope()
    val id = carte?.str("id").orEmpty()
    var nom by remember { mutableStateOf("") }
    var montant by remember { mutableStateOf("") }
    var libelle by remember { mutableStateOf("") }
    var date by remember { mutableStateOf("") }
    var credit by remember { mutableStateOf(false) }
    var texte by remember { mutableStateOf("") }
    var apercu by remember { mutableStateOf<JSONObject?>(null) }
    var erreur by remember { mutableStateOf<String?>(null) }
    var occupe by remember { mutableStateOf(false) }

    fun lancer(outil: String, args: JSONObject, ok: (JSONObject?) -> Unit) {
        occupe = true
        erreur = null
        scope.launch {
            val (e, data) = appeler(outil, args)
            occupe = false
            if (e != null) erreur = e else ok(data)
        }
    }

    val titre = when (action) {
        Action.OPERATION -> "Ajouter sur ${carte?.str("nom")}"
        Action.SOLDE -> "Recaler le solde"
        Action.IMPORT -> "Importer l'historique"
        Action.NOUVELLE -> "Nouveau compte"
    }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(titre) },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                when (action) {
                    Action.NOUVELLE -> {
                        OutlinedTextField(nom, { nom = it }, label = { Text("Nom (ex. Titres-restaurant)") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                        OutlinedTextField(montant, { montant = it }, label = { Text("Solde actuel (€)") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                    }
                    Action.OPERATION -> {
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            FilterChip(!credit, { credit = false }, label = { Text("Paiement") })
                            FilterChip(credit, { credit = true }, label = { Text("Crédit") })
                        }
                        OutlinedTextField(libelle, { libelle = it }, label = { Text("Libellé (vendeur)") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                        OutlinedTextField(montant, { montant = it }, label = { Text("Montant (€)") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                        OutlinedTextField(date, { date = it }, label = { Text("Date AAAA-MM-JJ (vide : aujourd'hui)") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                    }
                    Action.SOLDE -> {
                        Muted("Saisis le solde affiché par l'appli du fournisseur : l'écart devient un ajustement, ni revenu ni dépense.")
                        OutlinedTextField(montant, { montant = it }, label = { Text("Solde affiché (€)") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                    }
                    Action.IMPORT -> {
                        Muted("Colle l'historique copié depuis l'appli (Edenred…) ou un CSV date;libellé;montant.")
                        OutlinedTextField(texte, { texte = it; apercu = null }, label = { Text("Historique") }, minLines = 5, maxLines = 8, modifier = Modifier.fillMaxWidth())
                        apercu?.let {
                            Text(
                                "${it.int("nouvelles") ?: 0} nouvelle(s), ${it.int("deja_presentes") ?: 0} déjà présente(s), " +
                                    "${it.list("ignorees").size} ignorée(s).",
                                style = MaterialTheme.typography.bodyMedium,
                            )
                        }
                    }
                }
                erreur?.let { Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall) }
            }
        },
        confirmButton = {
            Button(enabled = !occupe, onClick = {
                val m = montant.replace(',', '.').trim()
                when (action) {
                    Action.NOUVELLE -> lancer("creer_carte", Engine.args("nom" to nom, "solde_initial" to (m.toDoubleOrNull() ?: 0.0))) { onDone("Carte créée.") }
                    Action.OPERATION -> {
                        val x = m.toDoubleOrNull()
                        if (x == null) erreur = "Montant illisible."
                        else lancer("carte_operation", Engine.args(
                            "carte" to id, "date" to date.ifBlank { java.time.LocalDate.now().toString() }, "montant" to x,
                            "libelle" to libelle, "type" to (if (credit) "credit" else "paiement"),
                        )) { onDone("Opération enregistrée.") }
                    }
                    Action.SOLDE -> {
                        val x = m.toDoubleOrNull()
                        if (x == null) erreur = "Montant illisible."
                        else lancer("carte_solde", Engine.args("carte" to id, "montant" to x)) { onDone("Solde recalé.") }
                    }
                    Action.IMPORT ->
                        if (apercu == null) lancer("carte_import", Engine.args("carte" to id, "texte" to texte, "apercu" to true)) { apercu = it }
                        else lancer("carte_import", Engine.args("carte" to id, "texte" to texte)) { onDone("Historique importé.") }
                }
            }) { Text(if (action == Action.IMPORT && apercu == null) "Aperçu" else "Enregistrer") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Annuler") } },
    )
}
