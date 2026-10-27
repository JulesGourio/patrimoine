package fr.julesgourio.patrimoine.ui.screens

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
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
import fr.julesgourio.patrimoine.ui.components.BarGroup
import fr.julesgourio.patrimoine.ui.components.CallScreen
import fr.julesgourio.patrimoine.ui.components.ChartSeries
import fr.julesgourio.patrimoine.ui.components.DonutChart
import fr.julesgourio.patrimoine.ui.components.HorizontalBars
import fr.julesgourio.patrimoine.ui.components.InteractiveLineChart
import fr.julesgourio.patrimoine.ui.components.Loaded
import fr.julesgourio.patrimoine.ui.components.Slice
import fr.julesgourio.patrimoine.ui.components.StackedBarChart
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

/** One (month, category) cell of `par_mois_et_categorie`; [mois] is « 2026-10 ». */
private class Cellule(val mois: String, val categorie: String, val montant: Double)

private fun cellules(d: JSONObject): List<Cellule> = d.list("par_mois_et_categorie").mapNotNull {
    val m = it.str("month")?.take(7) ?: return@mapNotNull null
    Cellule(m, it.str("category") ?: "Autres", it.num("amount") ?: 0.0)
}

private val MOIS_COURT = DateTimeFormatter.ofPattern("MMM yy", Locale.FRANCE)

private fun moisCourt(m: String): String = try {
    LocalDate.parse("$m-01").format(MOIS_COURT)
} catch (e: Exception) {
    m
}

/** Monthly bars stacked by category: the 6 biggest over the period, the rest as « Autres » (all if 7 or fewer). */
private fun groupes(cells: List<Cellule>): List<BarGroup> {
    val totaux = cells.groupBy { it.categorie }.mapValues { e -> e.value.sumOf { it.montant } }
    val noms = totaux.entries.sortedByDescending { it.value }.map { it.key }
    val gardees = if (noms.size <= 7) noms else noms.take(6)
    return cells.map { it.mois }.distinct().sorted().takeLast(12).map { m ->
        val duMois = cells.filter { it.mois == m }
        val parts = gardees.mapNotNull { c ->
            val v = duMois.filter { it.categorie == c }.sumOf { it.montant }
            if (v > 0) c to v else null
        }.toMutableList()
        val autres = duMois.filter { it.categorie !in gardees }.sumOf { it.montant }
        if (autres > 0) parts.add("Autres" to autres)
        BarGroup(moisCourt(m), parts, key = m)
    }
}

/** What the lists below the charts are narrowed to; [source] is the card that shows the list. */
private data class Filtre(
    val source: String,
    val titre: String,
    val categorie: String = "",
    val mois: String = "",
    val recherche: String = "",
)

/** The spending lines matching [f], most recent first. */
@Composable
private fun OperationsFiltrees(f: Filtre, onClose: () -> Unit) {
    val state = rememberCall(
        "operations",
        Engine.args(
            "recherche" to f.recherche, "jours" to 365, "flux_type" to "depense",
            "categorie" to f.categorie, "mois" to f.mois,
        ),
        f,
    )
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Text(f.titre, Modifier.weight(1f), style = MaterialTheme.typography.titleSmall)
        TextButton(onClick = onClose) { Text("Fermer") }
    }
    Loaded(state) { d ->
        val ops = d.list("operations")
        if (ops.isEmpty()) Muted("Aucune opération.")
        ops.take(40).forEach { o ->
            InfoRow(
                label = o.str("counterparty") ?: o.str("label") ?: "—",
                value = euros(o.num("montant"), sign = true),
                sub = day(o.str("date")) + (o.str("categorie")?.let { " · $it" } ?: ""),
            )
        }
        if (ops.size > 40 || d.bool("tronque")) Muted("Liste limitée : voir la recherche pour tout afficher.")
    }
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
    var moisSel by remember { mutableStateOf<String?>(null) }
    var filtre by remember { mutableStateOf<Filtre?>(null) }
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
            val cells = cellules(d)
            val barres = groupes(cells)
            val top = d.list("top_commercants").take(10)
            val aujourdhui = LocalDate.now()
            val moisCourant = aujourdhui.toString().take(7)

            if (erreur != null) item { Text(erreur.orEmpty(), color = MaterialTheme.colorScheme.error) }

            item {
                SectionCard("Ce mois-ci (${mois(aujourdhui.toString())})") {
                    InfoRow("Total dépensé", euros(total))
                    if (cats.isEmpty()) Muted("Aucune dépense ce mois-ci.")
                    val parts = cats.filter { it.depense > 0 }.map { Slice(it.nom, it.depense, key = it.nom) }
                    if (parts.isNotEmpty()) {
                        DonutChart(
                            parts, centerTitle = "Dépensé", centerValue = euros(total, cents = false),
                            modifier = Modifier.fillMaxWidth(),
                            onSliceClick = { sl ->
                                filtre = Filtre("ce_mois", "${sl.label} · ${mois(aujourdhui.toString())}",
                                    categorie = sl.key ?: sl.label, mois = moisCourant)
                            },
                        )
                    }
                    cats.forEach { c ->
                        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                            Box(Modifier.weight(1f)) { BudgetBar(c.nom, c.depense, c.budget) }
                            TextButton(onClick = { edit = c }) { Text("Budget") }
                        }
                    }
                    Muted("Le bouton Budget fixe un plafond mensuel par catégorie ; toucher une part du graphe liste les opérations.")
                    filtre?.takeIf { it.source == "ce_mois" }?.let { OperationsFiltrees(it) { filtre = null } }
                }
            }

            item {
                SectionCard("12 derniers mois") {
                    if (barres.isEmpty()) Muted("Pas encore de dépenses.")
                    else {
                        StackedBarChart(
                            barres, modifier = Modifier.fillMaxWidth(), selectedKey = moisSel,
                            onGroupClick = { g ->
                                moisSel = g.key
                                if (filtre?.source == "mois") filtre = null
                            },
                        )
                        Muted("Dépenses par mois et par catégorie. Touchez une barre pour voir le détail du mois.")
                    }
                    val m = moisSel
                    if (m != null) {
                        val duMois = cells.filter { it.mois == m && it.montant > 0 }
                            .groupBy { it.categorie }.map { (c, l) -> Slice(c, l.sumOf { it.montant }, key = c) }
                            .sortedByDescending { it.value }
                        InfoRow("Détail de ${mois("$m-01")}", euros(duMois.sumOf { it.value }))
                        if (duMois.isEmpty()) Muted("Aucune dépense ce mois-là.")
                        else HorizontalBars(
                            duMois, modifier = Modifier.fillMaxWidth(),
                            onClick = { sl ->
                                filtre = Filtre("mois", "${sl.label} · ${mois("$m-01")}",
                                    categorie = sl.key ?: sl.label, mois = m)
                            },
                        )
                        filtre?.takeIf { it.source == "mois" }?.let { OperationsFiltrees(it) { filtre = null } }
                    }
                }
            }

            item {
                SectionCard("Revenus et dépenses") {
                    if (fluxRows.isEmpty()) Muted("Données de flux indisponibles.")
                    else {
                        fun serie(nom: String, cle: String) = ChartSeries(
                            nom,
                            fluxRows.mapNotNull { r ->
                                val m = r.str("month")?.take(10)
                                val v = r.num(cle)
                                if (m != null && v != null) m to v else null
                            },
                        )
                        InteractiveLineChart(
                            listOf(
                                serie("Revenus (hors héritages et donations)", "revenus"),
                                serie("Dépenses nettes des remboursements", "depenses"),
                            ),
                            modifier = Modifier.fillMaxWidth(),
                            showPeriods = false,
                            showChange = false,
                        )
                        Text("Taux d'épargne", style = MaterialTheme.typography.titleSmall)
                        InteractiveLineChart(
                            listOf(serie("Taux d'épargne", "taux_epargne")),
                            modifier = Modifier.fillMaxWidth(),
                            showPeriods = false,
                            showChange = false,
                            valueFormat = { pct(it, sign = false) },
                        )
                    }
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
                    Muted("Dépenses nettes des remboursements ; revenus hors héritages et donations ; épargne = revenus - dépenses.")
                }
            }

            item {
                SectionCard("Top 10 des commerçants (12 mois)") {
                    if (top.isEmpty()) Muted("Aucun commerçant.")
                    else HorizontalBars(
                        top.map { t -> Slice(t.str("merchant") ?: "—", t.num("sum") ?: 0.0, key = t.str("merchant")) },
                        modifier = Modifier.fillMaxWidth(),
                        onClick = { sl ->
                            val nom = sl.key ?: sl.label
                            filtre = Filtre("commercant", nom, recherche = nom)
                        },
                    )
                    filtre?.takeIf { it.source == "commercant" }?.let { OperationsFiltrees(it) { filtre = null } }
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
