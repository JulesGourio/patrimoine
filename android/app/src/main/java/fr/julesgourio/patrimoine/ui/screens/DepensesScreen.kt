package fr.julesgourio.patrimoine.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Checkbox
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
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
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.navigation.NavController
import fr.julesgourio.patrimoine.engine.Engine
import fr.julesgourio.patrimoine.engine.Reply
import fr.julesgourio.patrimoine.ui.Routes
import fr.julesgourio.patrimoine.ui.components.BudgetBar
import fr.julesgourio.patrimoine.ui.components.CallScreen
import fr.julesgourio.patrimoine.ui.components.InfoRow
import fr.julesgourio.patrimoine.ui.components.Load
import fr.julesgourio.patrimoine.ui.components.Muted
import fr.julesgourio.patrimoine.ui.components.ScreenScaffold
import fr.julesgourio.patrimoine.ui.components.SectionCard
import fr.julesgourio.patrimoine.ui.components.bool
import fr.julesgourio.patrimoine.ui.components.day
import fr.julesgourio.patrimoine.ui.components.euros
import fr.julesgourio.patrimoine.ui.components.list
import fr.julesgourio.patrimoine.ui.components.num
import fr.julesgourio.patrimoine.ui.components.numbers
import fr.julesgourio.patrimoine.ui.components.objOrNull
import fr.julesgourio.patrimoine.ui.components.pct
import fr.julesgourio.patrimoine.ui.components.rememberCall
import fr.julesgourio.patrimoine.ui.components.str
import fr.julesgourio.patrimoine.ui.components.strings
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import org.json.JSONObject
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.util.Locale

private val MOIS_FMT = DateTimeFormatter.ofPattern("MMM yyyy", Locale.FRANCE)

/** « oct. 2026 » from an ISO date. */
private fun mois(iso: String): String = try {
    LocalDate.parse(iso.take(10)).format(MOIS_FMT)
} catch (e: Exception) {
    iso
}

/** Runs a tool and reports the outcome; a tool answering `{"erreur": …}` counts as a failure. */
private suspend fun appeler(name: String, args: JSONObject, ok: () -> Unit, err: (String) -> Unit) {
    when (val r = Engine.call(name, args)) {
        is Reply.Ok -> {
            val e = (r.data as? JSONObject)?.str("erreur")
            if (e != null) err(e) else ok()
        }
        is Reply.Err -> err(r.message)
    }
}

private data class Categorie(val nom: String, val depense: Double, val budget: Double?)

private fun categories(cur: JSONObject?): List<Categorie> {
    if (cur == null) return emptyList()
    return cur.keys().asSequence().map { k ->
        val o = cur.objOrNull(k)
        Categorie(k, o?.num("depense") ?: 0.0, o?.num("budget"))
    }.sortedByDescending { it.depense }.toList()
}

private fun montantTexte(x: Double): String = if (x % 1.0 == 0.0) x.toInt().toString() else x.toString()

// --- Dépenses --------------------------------------------------------------------------------------------------

@Composable
fun DepensesScreen(nav: NavController) {
    val dep = rememberCall("depenses", Engine.args("mois" to 12))
    val flux = rememberCall("flux", Engine.args("mois" to 12))
    val fluxRows = (flux.load as? Load.Done)?.data?.list("flux").orEmpty()
    var edit by remember { mutableStateOf<Categorie?>(null) }
    var erreur by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()

    ScreenScaffold(
        "Dépenses",
        actions = {
            IconButton(onClick = { nav.navigate(Routes.OPERATIONS) }) {
                Icon(Icons.Filled.Search, contentDescription = "Rechercher dans les opérations")
            }
        },
    ) { padding ->
        CallScreen(dep, padding) { d ->
            val cats = categories(d.objOrNull("mois_en_cours"))
            val total = cats.sumOf { it.depense }
            val parMois = d.objOrNull("par_mois")?.numbers().orEmpty().sortedBy { it.first }.takeLast(12)
            val maxMois = parMois.maxOfOrNull { it.second } ?: 0.0
            val top = d.list("top_commercants").take(10)
            val aujourdhui = LocalDate.now()

            if (erreur != null) item { Text(erreur.orEmpty(), color = MaterialTheme.colorScheme.error) }

            item {
                SectionCard("Ce mois-ci (${mois(aujourdhui.toString())})") {
                    InfoRow("Total dépensé", euros(total))
                    if (cats.isEmpty()) Muted("Aucune dépense ce mois-ci.")
                    cats.forEach { c ->
                        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                            Box(Modifier.weight(1f)) { BudgetBar(c.nom, c.depense, c.budget) }
                            TextButton(onClick = { edit = c }) { Text("Budget") }
                        }
                    }
                    Muted("Le bouton Budget fixe un plafond mensuel par catégorie.")
                }
            }

            item {
                SectionCard("12 derniers mois") {
                    if (parMois.isEmpty()) Muted("Pas encore de dépenses.")
                    parMois.forEach { (m, x) ->
                        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                            Text(mois(m), Modifier.width(84.dp), style = MaterialTheme.typography.bodySmall)
                            Box(Modifier.weight(1f).padding(horizontal = 8.dp)) {
                                val fraction = if (maxMois > 0) (x / maxMois).toFloat().coerceIn(0f, 1f) else 0f
                                Box(
                                    Modifier.fillMaxWidth(fraction).height(14.dp)
                                        .background(MaterialTheme.colorScheme.primary, RoundedCornerShape(3.dp)),
                                )
                            }
                            Text(euros(x, cents = false), style = MaterialTheme.typography.bodySmall)
                        }
                    }
                }
            }

            item {
                SectionCard("Taux d'épargne") {
                    if (fluxRows.isEmpty()) Muted("Données de flux indisponibles.")
                    fluxRows.takeLast(6).reversed().forEach { r ->
                        val m = r.str("month").orEmpty()
                        val enCours = m.take(7) == aujourdhui.toString().take(7)
                        InfoRow(
                            label = mois(m) + if (enCours) " (en cours)" else "",
                            value = euros(r.num("epargne"), sign = true),
                            tone = r.num("epargne"),
                            sub = "Revenus ${euros(r.num("revenus"))} · Dépenses ${euros(r.num("depenses"))}" +
                                " · taux ${pct(r.num("taux_epargne"), sign = false)}",
                        )
                    }
                    Muted("Dépenses nettes des remboursements ; épargne = revenus - dépenses.")
                }
            }

            item {
                SectionCard("Top 10 des commerçants (12 mois)") {
                    if (top.isEmpty()) Muted("Aucun commerçant.")
                    top.forEach { t ->
                        val n = t.num("count")?.toInt()
                        InfoRow(
                            label = t.str("merchant") ?: "—",
                            value = euros(t.num("sum")),
                            sub = n?.let { "$it opération" + if (it > 1) "s" else "" },
                        )
                    }
                }
            }
        }
    }

    val cible = edit
    if (cible != null) {
        var texte by remember(cible.nom) { mutableStateOf(cible.budget?.let { montantTexte(it) }.orEmpty()) }
        val montant = texte.trim().replace(',', '.').toDoubleOrNull()
        fun fixer(valeur: Double) {
            scope.launch {
                appeler(
                    "budget",
                    Engine.args("categorie" to cible.nom, "montant_mensuel" to valeur),
                    ok = { erreur = null; edit = null; dep.reload() },
                    err = { erreur = it; edit = null },
                )
            }
        }
        AlertDialog(
            onDismissRequest = { edit = null },
            title = { Text("Budget : ${cible.nom}") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("Budget mensuel en euros. Le retirer supprime le plafond.")
                    OutlinedTextField(
                        value = texte,
                        onValueChange = { texte = it },
                        label = { Text("Montant mensuel (€)") },
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                    )
                }
            },
            confirmButton = {
                TextButton(enabled = montant != null && montant > 0, onClick = { fixer(montant ?: 0.0) }) {
                    Text("Fixer")
                }
            },
            dismissButton = {
                Row {
                    if (cible.budget != null) TextButton(onClick = { fixer(0.0) }) { Text("Retirer") }
                    TextButton(onClick = { edit = null }) { Text("Annuler") }
                }
            },
        )
    }
}

// --- Opérations ------------------------------------------------------------------------------------------------

private val FLUX_FILTRES = listOf("Toutes" to "", "Dépenses" to "depense", "Revenus" to "revenu", "Interne" to "interne")
private val PERIODES = listOf("30 j" to 30, "90 j" to 90, "1 an" to 365)

@Composable
fun OperationsScreen(onBack: () -> Unit) {
    var saisie by remember { mutableStateOf("") }
    var q by remember { mutableStateOf("") }
    var flux by remember { mutableStateOf("") }
    var jours by remember { mutableStateOf(90) }
    var cible by remember { mutableStateOf<JSONObject?>(null) }
    var erreur by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()

    LaunchedEffect(saisie) {
        delay(400)
        q = saisie.trim()
    }

    val state = rememberCall(
        "operations",
        Engine.args("recherche" to q, "jours" to jours, "flux_type" to flux),
        q, jours, flux,
    )
    val refs = rememberCall("references")

    ScreenScaffold("Opérations", onBack = onBack) { padding ->
        Column(Modifier.padding(padding)) {
            Column(
                Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                OutlinedTextField(
                    value = saisie,
                    onValueChange = { saisie = it },
                    modifier = Modifier.fillMaxWidth(),
                    label = { Text("Rechercher (libellé ou commerçant)") },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(imeAction = ImeAction.Search),
                    keyboardActions = KeyboardActions(onSearch = { q = saisie.trim() }),
                )
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    FLUX_FILTRES.forEach { (nom, valeur) ->
                        FilterChip(selected = flux == valeur, onClick = { flux = valeur }, label = { Text(nom) })
                    }
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    PERIODES.forEach { (nom, valeur) ->
                        FilterChip(selected = jours == valeur, onClick = { jours = valeur }, label = { Text(nom) })
                    }
                }
                if (erreur != null) Text(erreur.orEmpty(), color = MaterialTheme.colorScheme.error)
            }
            Box(Modifier.weight(1f)) {
                CallScreen(state) { d ->
                    val ops = d.list("operations")
                    if (ops.isEmpty()) item { Muted("Aucune opération pour ces critères.") }
                    items(ops) { o ->
                        val type = o.str("flow")
                        val modifiable = type == "depense" || type == "revenu"
                        val montant = o.num("montant")
                        Column {
                            InfoRow(
                                label = o.str("counterparty") ?: o.str("label") ?: "—",
                                value = euros(montant, sign = true),
                                tone = if (type == "interne") null else montant,
                                sub = day(o.str("date")) + (o.str("categorie")?.let { " · $it" } ?: "") +
                                    if (type == "interne") " · virement interne" else "",
                                onClick = if (modifiable) ({ cible = o }) else null,
                            )
                            HorizontalDivider(Modifier.padding(top = 8.dp))
                        }
                    }
                    if (d.bool("tronque")) {
                        item { Muted("Liste tronquée à 300 : affinez la recherche ou la période.") }
                    }
                }
            }
        }
    }

    val op = cible
    if (op != null) {
        val type = op.str("flow")
        val liste = (refs.load as? Load.Done)?.data
            ?.strings(if (type == "revenu") "categories_revenus" else "categories_depenses").orEmpty()
        val commercant = op.str("counterparty")
        var choix by remember(op.str("id")) { mutableStateOf(op.str("categorie")) }
        var tout by remember(op.str("id")) { mutableStateOf(false) }
        AlertDialog(
            onDismissRequest = { cible = null },
            title = { Text("Recatégoriser", maxLines = 2, overflow = TextOverflow.Ellipsis) },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Muted((commercant ?: op.str("label") ?: "—") + " · " + euros(op.num("montant"), sign = true))
                    if (liste.isEmpty()) Muted("Liste des catégories indisponible.")
                    Column(Modifier.heightIn(max = 320.dp).verticalScroll(rememberScrollState())) {
                        liste.forEach { c ->
                            Row(
                                Modifier.fillMaxWidth().clickable { choix = c },
                                verticalAlignment = Alignment.CenterVertically,
                            ) {
                                RadioButton(selected = choix == c, onClick = { choix = c })
                                Text(c)
                            }
                        }
                    }
                    if (commercant != null) {
                        Row(
                            Modifier.fillMaxWidth().clickable { tout = !tout },
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Checkbox(checked = tout, onCheckedChange = { tout = it })
                            Text("Appliquer à tout ce commerçant")
                        }
                    }
                }
            },
            confirmButton = {
                TextButton(
                    enabled = choix != null && choix in liste,
                    onClick = {
                        val id = op.str("id")
                        val categorie = choix
                        if (id != null && categorie != null) {
                            scope.launch {
                                appeler(
                                    "categoriser",
                                    Engine.args(
                                        "transaction_id" to id,
                                        "categorie" to categorie,
                                        "tout_le_commercant" to (tout && commercant != null),
                                    ),
                                    ok = { erreur = null; cible = null; state.reload() },
                                    err = { erreur = it; cible = null },
                                )
                            }
                        }
                    },
                ) { Text("Appliquer") }
            },
            dismissButton = { TextButton(onClick = { cible = null }) { Text("Annuler") } },
        )
    }
}
