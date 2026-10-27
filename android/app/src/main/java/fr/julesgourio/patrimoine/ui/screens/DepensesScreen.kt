package fr.julesgourio.patrimoine.ui.screens

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.navigation.NavController
import fr.julesgourio.patrimoine.engine.Engine
import fr.julesgourio.patrimoine.engine.Reply
import fr.julesgourio.patrimoine.ui.Routes
import fr.julesgourio.patrimoine.ui.components.BarGroup
import fr.julesgourio.patrimoine.ui.components.CallScreen
import fr.julesgourio.patrimoine.ui.components.ChartSeries
import fr.julesgourio.patrimoine.ui.components.InfoRow
import fr.julesgourio.patrimoine.ui.components.InteractiveLineChart
import fr.julesgourio.patrimoine.ui.components.Load
import fr.julesgourio.patrimoine.ui.components.Muted
import fr.julesgourio.patrimoine.ui.components.ScreenScaffold
import fr.julesgourio.patrimoine.ui.components.SectionCard
import fr.julesgourio.patrimoine.ui.components.StackedBarChart
import fr.julesgourio.patrimoine.ui.components.bool
import fr.julesgourio.patrimoine.ui.components.chartPalette
import fr.julesgourio.patrimoine.ui.components.day
import fr.julesgourio.patrimoine.ui.components.euros
import fr.julesgourio.patrimoine.ui.components.gainColor
import fr.julesgourio.patrimoine.ui.components.list
import fr.julesgourio.patrimoine.ui.components.num
import fr.julesgourio.patrimoine.ui.components.objOrNull
import fr.julesgourio.patrimoine.ui.components.pct
import fr.julesgourio.patrimoine.ui.components.rememberCall
import fr.julesgourio.patrimoine.ui.components.str
import fr.julesgourio.patrimoine.ui.components.strings
import fr.julesgourio.patrimoine.ui.theme.LocalMoney
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import org.json.JSONObject
import java.time.LocalDate
import java.time.YearMonth
import java.time.format.DateTimeFormatter
import java.util.Locale

private val MOIS_LONG = DateTimeFormatter.ofPattern("MMMM yyyy", Locale.FRANCE)
private val MOIS_COURT = DateTimeFormatter.ofPattern("MMM yy", Locale.FRANCE)
private val AMBRE = Color(0xFFFFB020)

/** « Octobre 2026 » from « 2026-10 ». */
private fun moisLong(m: String): String = try {
    YearMonth.parse(m).format(MOIS_LONG).replaceFirstChar { it.uppercase() }
} catch (e: Exception) {
    m
}

private fun moisCourt(m: String): String = try {
    YearMonth.parse(m).format(MOIS_COURT)
} catch (e: Exception) {
    m
}

/** « oct. 2026 » from an ISO date. */
private fun mois(iso: String): String = try {
    LocalDate.parse(iso.take(10)).format(DateTimeFormatter.ofPattern("MMM yyyy", Locale.FRANCE))
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

/** One spending line of `depenses_ecran` ; [date] and [mois] are ISO (« 2026-10-03 », « 2026-10 »). */
private class Op(
    val id: String,
    val date: String,
    val commercant: String,
    val categorie: String,
    val modifiee: Boolean,
    val montant: Double,
    val contrepartie: String = "",
) {
    val mois: String get() = date.take(7)
}

private fun operations(d: JSONObject): List<Op> = d.list("operations").mapNotNull { o ->
    val id = o.str("id") ?: return@mapNotNull null
    val date = o.str("date")?.take(10) ?: return@mapNotNull null
    Op(id, date, o.str("commercant") ?: "—", o.str("categorie") ?: "Non catégorisé", o.bool("modifiee"),
        o.num("montant") ?: 0.0, o.str("contrepartie")?.trim().orEmpty())
}

/** The 13 months ending with the current one, oldest first. */
private fun treizeMois(): List<String> {
    val fin = YearMonth.now()
    return (12 downTo 0).map { fin.minusMonths(it.toLong()).toString() }
}

/** Monthly bars stacked by category: the 6 biggest over the period, the rest as « Autres » (all if 7 or fewer). */
private fun groupes(ops: List<Op>, months: List<String>): List<BarGroup> {
    val totaux = ops.groupBy { it.categorie }.mapValues { e -> e.value.sumOf { it.montant } }
    val noms = totaux.entries.sortedByDescending { it.value }.map { it.key }
    val gardees = if (noms.size <= 7) noms else noms.take(6)
    return months.map { m ->
        val duMois = ops.filter { it.mois == m }
        val parts = gardees.mapNotNull { c ->
            val v = duMois.filter { it.categorie == c }.sumOf { it.montant }
            if (v > 0) c to v else null
        }.toMutableList()
        val autres = duMois.filter { it.categorie !in gardees }.sumOf { it.montant }
        if (autres > 0) parts.add("Autres" to autres)
        BarGroup(moisCourt(m), parts, key = m)
    }
}

private fun montantTexte(x: Double): String = if (x % 1.0 == 0.0) x.toInt().toString() else x.toString()

// --- Dépenses --------------------------------------------------------------------------------------------------

@Composable
fun DepensesScreen(nav: NavController) {
    val ecran = rememberCall("depenses_ecran", Engine.args("mois" to 13))
    var edit by remember { mutableStateOf<Categorie?>(null) }
    var recat by remember { mutableStateOf<Op?>(null) }
    var erreur by remember { mutableStateOf<String?>(null) }
    var moisSel by remember { mutableStateOf(YearMonth.now().toString()) }
    var catSel by remember { mutableStateOf<String?>(null) }
    var jourSel by remember { mutableStateOf<String?>(null) }
    var recherche by remember { mutableStateOf("") }
    val scope = rememberCoroutineScope()

    ScreenScaffold(
        "Dépenses",
        actions = {
            IconButton(onClick = { nav.navigate(Routes.OPERATIONS) }) {
                Icon(Icons.Filled.Search, contentDescription = "Rechercher dans les opérations")
            }
        },
    ) { padding ->
        CallScreen(ecran, padding) { d ->
            val ops = operations(d)
            val months = treizeMois()
            val courant = months.last()
            val premier = ops.minOfOrNull { it.mois }
            val complets = months.filter { premier != null && it >= premier && it < courant }
            val moyenne = if (complets.isEmpty()) 0.0 else complets.sumOf { m -> ops.filter { it.mois == m }.sumOf { it.montant } } / complets.size
            val barres = groupes(ops, months)
            val chartCats = barres.flatMap { g -> g.parts.map { it.first } }.toSortedSet().toList()
            val palette = chartPalette(chartCats.size)
            val gris = Color(0xFF9E9E9E)
            val couleur: (String) -> Color = { c ->
                val i = chartCats.indexOf(c).takeIf { it >= 0 } ?: chartCats.indexOf("Autres")
                if (i >= 0) palette[i] else gris
            }
            val budgets = d.objOrNull("mois_en_cours")
            fun budgetDe(c: String): Double? = budgets?.objOrNull(c)?.num("budget")

            val idx = months.indexOf(moisSel).coerceAtLeast(0)
            val sel = months[idx]
            val duMois = ops.filter { it.mois == sel }
            val total = duMois.sumOf { it.montant }
            val parCat = duMois.groupBy { it.categorie }.mapValues { e -> e.value.sumOf { it.montant } }
            val cats = (parCat.keys + (budgets?.keys()?.asSequence()?.filter { budgetDe(it) != null }?.toList().orEmpty()))
                .distinct().map { Categorie(it, parCat[it] ?: 0.0, budgetDe(it)) }
                .sortedByDescending { it.depense }
            val maxCat = cats.maxOfOrNull { it.depense }?.takeIf { it > 0 } ?: 1.0
            fun moyenneCat(c: String): Double =
                if (complets.isEmpty()) 0.0 else ops.filter { it.categorie == c && it.mois in complets }.sumOf { it.montant } / complets.size

            fun changerMois(m: String) { moisSel = m; catSel = null; jourSel = null }

            if (erreur != null) item { Text(erreur.orEmpty(), color = MaterialTheme.colorScheme.error) }

            // (1) En-tête : mois, total, écart à la moyenne, barres des 13 derniers mois.
            item {
                SectionCard {
                    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                        TextButton(enabled = idx > 0, onClick = { changerMois(months[idx - 1]) }) { Text("‹", style = MaterialTheme.typography.titleLarge) }
                        Text(moisLong(sel), Modifier.weight(1f), textAlign = TextAlign.Center,
                            style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                        TextButton(enabled = idx < months.lastIndex, onClick = { changerMois(months[idx + 1]) }) { Text("›", style = MaterialTheme.typography.titleLarge) }
                    }
                    Text(euros(total, cents = false), style = MaterialTheme.typography.displaySmall, fontWeight = FontWeight.SemiBold)
                    val ecart = total - moyenne
                    val detail = "${duMois.size} opérations · panier moyen ${euros(total / maxOf(1, duMois.size), cents = true)}"
                    val teinte = gainColor(-ecart)
                    Text(buildAnnotatedString {
                        if (complets.isNotEmpty()) {
                            withStyle(SpanStyle(color = teinte)) { append(euros(ecart, sign = true)) }
                            append(" vs moyenne (${euros(moyenne)}) · ")
                        }
                        append(detail)
                    }, style = MaterialTheme.typography.bodyMedium)
                    StackedBarChart(
                        barres, modifier = Modifier.fillMaxWidth(), selectedKey = sel,
                        limitLine = moyenne.takeIf { it > 0 },
                        onGroupClick = { g -> g.key?.let { changerMois(it) } },
                    )
                    Muted("Touchez une barre pour changer de mois. Ligne = moyenne mensuelle des mois complets.")
                }
            }

            // (2) Catégories du mois.
            item {
                SectionCard("Catégories du mois") {
                    if (cats.isEmpty()) Muted("Aucune dépense ce mois-là.")
                    cats.forEach { c ->
                        val b = c.budget
                        val ratio = if (b != null && b > 0) c.depense / b else c.depense / maxCat
                        val depasse = b != null && b > 0 && c.depense > b
                        val barre = when {
                            depasse -> LocalMoney.current.loss
                            b != null && b > 0 && ratio > 0.8 -> AMBRE
                            else -> couleur(c.nom)
                        }
                        val av = moyenneCat(c.nom)
                        Column(
                            Modifier.fillMaxWidth().clickable { catSel = if (catSel == c.nom) null else c.nom }
                                .let { if (catSel == c.nom) it.border(1.dp, MaterialTheme.colorScheme.primary, RoundedCornerShape(8.dp)) else it }
                                .padding(horizontal = 6.dp, vertical = 4.dp),
                            verticalArrangement = Arrangement.spacedBy(4.dp),
                        ) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Pastille(couleur(c.nom))
                                Spacer(Modifier.width(8.dp))
                                Text(c.nom, Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
                                Text(euros(c.depense), fontWeight = FontWeight.Medium)
                                if (b != null) Text(" / ${euros(b)}", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                IconButton(onClick = { edit = c }, modifier = Modifier.size(32.dp)) {
                                    Icon(Icons.Filled.Edit, contentDescription = "Budget : ${c.nom}", Modifier.size(16.dp))
                                }
                            }
                            LinearProgressIndicator(
                                progress = { ratio.toFloat().coerceIn(0f, 1f) },
                                modifier = Modifier.fillMaxWidth(), color = barre,
                            )
                            Text(
                                (if (av > 0) "${euros(c.depense - av, sign = true)} vs moyenne (${euros(av)})" else "nouvelle catégorie") +
                                    if (depasse) " · budget dépassé" else "",
                                style = MaterialTheme.typography.bodySmall,
                                color = if (depasse) LocalMoney.current.loss else MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    }
                    Muted("Touchez une catégorie pour ne voir que ses opérations ; le crayon fixe un budget mensuel.")
                }
            }

            // (3) Calendrier du mois.
            item {
                SectionCard("Calendrier") {
                    val premierJour = YearMonth.parse(sel).atDay(1)
                    val nbJours = YearMonth.parse(sel).lengthOfMonth()
                    val decalage = premierJour.dayOfWeek.value - 1
                    val parJour = duMois.filter { catSel == null || it.categorie == catSel }.groupBy { it.date }
                        .mapValues { e -> e.value.sumOf { it.montant } }
                    val maxJour = maxOf(1.0, parJour.values.maxOrNull() ?: 0.0)
                    Row(Modifier.fillMaxWidth()) {
                        listOf("L", "M", "M", "J", "V", "S", "D").forEach {
                            Text(it, Modifier.weight(1f), textAlign = TextAlign.Center, style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                    val cases: List<Int?> = List(decalage) { null } + (1..nbJours).toList()
                    cases.chunked(7).forEach { semaine ->
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                            (semaine + List(7 - semaine.size) { null }).forEach { n ->
                                if (n == null) Spacer(Modifier.weight(1f))
                                else {
                                    val iso = "$sel-${n.toString().padStart(2, '0')}"
                                    val v = parJour[iso] ?: 0.0
                                    val alpha = if (v > 0) 0.2f + 0.8f * minOf(1.0, v / maxJour).toFloat() else 0.05f
                                    val choisi = jourSel == iso
                                    Box(
                                        Modifier.weight(1f).aspectRatio(1f).clip(RoundedCornerShape(6.dp))
                                            .background(MaterialTheme.colorScheme.primary.copy(alpha = alpha))
                                            .let { if (choisi) it.border(2.dp, MaterialTheme.colorScheme.onSurface, RoundedCornerShape(6.dp)) else it }
                                            .clickable { jourSel = if (choisi) null else iso },
                                        contentAlignment = Alignment.Center,
                                    ) { Text(n.toString(), style = MaterialTheme.typography.labelSmall) }
                                }
                            }
                        }
                    }
                    Muted("Plus la case est foncée, plus la dépense du jour est forte. Touchez un jour pour ne voir que ses dépenses.")
                }
            }

            // (4) Opérations du mois, filtrées.
            item {
                SectionCard("Opérations") {
                    OutlinedTextField(
                        value = recherche, onValueChange = { recherche = it },
                        modifier = Modifier.fillMaxWidth(), singleLine = true,
                        label = { Text("Rechercher un commerçant…") },
                    )
                    if (catSel != null || jourSel != null) {
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            catSel?.let { FilterChip(selected = true, onClick = { catSel = null }, label = { Text("$it ✕") }) }
                            jourSel?.let { FilterChip(selected = true, onClick = { jourSel = null }, label = { Text("${day(it)} ✕") }) }
                        }
                    }
                    val q = recherche.trim().lowercase()
                    val liste = duMois.filter {
                        (catSel == null || it.categorie == catSel) && (jourSel == null || it.date == jourSel) &&
                            (q.isEmpty() || (it.commercant + " " + it.categorie).lowercase().contains(q))
                    }
                    if (liste.isEmpty()) Muted("Aucune opération.")
                    liste.take(30).forEach { o ->
                        Row(
                            Modifier.fillMaxWidth().clickable { recat = o }.padding(vertical = 6.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Column(Modifier.weight(1f)) {
                                Text(o.commercant, maxLines = 1, overflow = TextOverflow.Ellipsis)
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Text(day(o.date) + " · ", style = MaterialTheme.typography.bodySmall,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                                    Pastille(couleur(o.categorie), 8)
                                    Text(" ${o.categorie}", style = MaterialTheme.typography.bodySmall,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 1, overflow = TextOverflow.Ellipsis)
                                    if (o.modifiee) {
                                        Spacer(Modifier.width(6.dp))
                                        Surface(shape = RoundedCornerShape(4.dp), color = MaterialTheme.colorScheme.secondaryContainer) {
                                            Text("modifiée", Modifier.padding(horizontal = 4.dp), style = MaterialTheme.typography.labelSmall)
                                        }
                                    }
                                }
                            }
                            Text(euros(o.montant, cents = true), fontWeight = FontWeight.Medium)
                        }
                        HorizontalDivider()
                    }
                    if (liste.size > 30) Muted("${liste.size - 30} autres opérations : affinez avec la recherche ou un filtre.")
                    Muted("Touchez une opération pour changer sa catégorie.")
                }
            }

            // (5) Revenus, dépenses, épargne.
            item {
                val fluxRows = d.list("flux")
                SectionCard("Revenus, dépenses, épargne") {
                    if (fluxRows.isEmpty()) Muted("Données de flux indisponibles.")
                    else {
                        fun serie(nom: String, cle: String, sans: String? = null) = ChartSeries(
                            nom,
                            fluxRows.mapNotNull { r ->
                                val m = r.str("month")?.take(10)
                                val v = r.num(cle)
                                if (m != null && v != null && m.take(7) != sans) m to v else null
                            },
                        )
                        InteractiveLineChart(
                            listOf(
                                serie("Revenus (hors héritages et donations)", "revenus"),
                                serie("Dépenses nettes des remboursements", "depenses"),
                                serie("Épargne", "epargne"),
                            ),
                            modifier = Modifier.fillMaxWidth(), showPeriods = false, showChange = false,
                        )
                        Text("Taux d'épargne", style = MaterialTheme.typography.titleSmall)
                        InteractiveLineChart(
                            listOf(serie("Taux d'épargne", "taux_epargne", sans = courant)),
                            modifier = Modifier.fillMaxWidth(), showPeriods = false, showChange = false,
                            valueFormat = { pct(it, sign = false) },
                        )
                    }
                    Muted("Dépenses nettes des remboursements ; héritages et donations à part. Mois en cours incomplet.")
                    Muted("Le taux d'épargne exclut le mois en cours tant que le salaire n'est pas tombé.")
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
                    ok = { erreur = null; edit = null; ecran.reload() },
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

    val op = recat
    val data = (ecran.load as? Load.Done)?.data
    if (op != null && data != null) {
        FeuilleCategorie(
            op = op,
            categories = data.strings("categories"),
            onClose = { recat = null },
            onApply = { categorie, tout ->
                scope.launch {
                    appeler(
                        "categoriser",
                        Engine.args("transaction_id" to op.id, "categorie" to categorie, "tout_le_commercant" to tout),
                        ok = { erreur = null; recat = null; ecran.reload() },
                        err = { erreur = it; recat = null },
                    )
                }
            },
        )
    }
}

/** A coloured dot, as in the chart's legend. */
@Composable
private fun Pastille(couleur: Color, taille: Int = 10) {
    Box(Modifier.size(taille.dp).background(couleur, CircleShape))
}

/** Bottom sheet to change one operation's category (alone, or for every operation of the same merchant). */
@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
@Composable
private fun FeuilleCategorie(
    op: Op,
    categories: List<String>,
    onClose: () -> Unit,
    onApply: (String, Boolean) -> Unit,
) {
    var choix by remember(op.id) { mutableStateOf(op.categorie) }
    var tout by remember(op.id) { mutableStateOf(false) }
    ModalBottomSheet(onDismissRequest = onClose, sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)) {
        Column(
            Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).padding(horizontal = 16.dp, vertical = 8.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Row(Modifier.fillMaxWidth()) {
                Text(op.commercant, Modifier.weight(1f), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold,
                    maxLines = 2, overflow = TextOverflow.Ellipsis)
                Text(euros(op.montant, cents = true), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
            }
            Muted("${day(op.date)} · catégorie actuelle : ${op.categorie}")
            Text("Recatégoriser", style = MaterialTheme.typography.titleSmall)
            if (categories.isEmpty()) Muted("Liste des catégories indisponible.")
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                categories.forEach { c ->
                    FilterChip(selected = choix == c, onClick = { choix = c }, label = { Text(c) })
                }
            }
            if (op.contrepartie.isNotEmpty()) {
                Row(Modifier.fillMaxWidth().clickable { tout = !tout }, verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(checked = tout, onCheckedChange = { tout = it })
                    Text("Appliquer à toutes les opérations de ce commerçant")
                }
            }
            Row(Modifier.fillMaxWidth().padding(bottom = 16.dp), horizontalArrangement = Arrangement.spacedBy(8.dp, Alignment.End)) {
                TextButton(onClick = onClose) { Text("Annuler") }
                Button(enabled = choix in categories, onClick = { onApply(choix, tout && op.contrepartie.isNotEmpty()) }) { Text("Appliquer") }
            }
        }
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
