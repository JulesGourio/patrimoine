package fr.julesgourio.patrimoine.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBars
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.lazy.items
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
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.navigation.NavController
import fr.julesgourio.patrimoine.engine.Engine
import fr.julesgourio.patrimoine.engine.Reply
import fr.julesgourio.patrimoine.ui.Routes
import fr.julesgourio.patrimoine.ui.components.BarreFlux
import fr.julesgourio.patrimoine.ui.components.BarreRepartition
import fr.julesgourio.patrimoine.ui.components.CallScreen
import fr.julesgourio.patrimoine.ui.components.Carte
import fr.julesgourio.patrimoine.ui.components.CarteEntete
import fr.julesgourio.patrimoine.ui.components.CouleurDepenses
import fr.julesgourio.patrimoine.ui.components.CourbeTaux
import fr.julesgourio.patrimoine.ui.components.BarGroup
import fr.julesgourio.patrimoine.ui.components.GraphiqueFlux
import fr.julesgourio.patrimoine.ui.components.LigneInfobulle
import fr.julesgourio.patrimoine.ui.components.StackedBarChart
import fr.julesgourio.patrimoine.ui.components.GrilleIndicateurs
import fr.julesgourio.patrimoine.ui.components.Indicateur
import fr.julesgourio.patrimoine.ui.components.InfoRow
import fr.julesgourio.patrimoine.ui.components.LigneListe
import fr.julesgourio.patrimoine.ui.components.LigneRepartition
import fr.julesgourio.patrimoine.ui.components.Load
import fr.julesgourio.patrimoine.ui.components.Muted
import fr.julesgourio.patrimoine.ui.components.ScreenScaffold
import fr.julesgourio.patrimoine.ui.components.bool
import fr.julesgourio.patrimoine.ui.components.dateCourte
import fr.julesgourio.patrimoine.ui.components.day
import fr.julesgourio.patrimoine.ui.components.euros
import fr.julesgourio.patrimoine.ui.components.initiales
import fr.julesgourio.patrimoine.ui.components.list
import fr.julesgourio.patrimoine.ui.components.num
import fr.julesgourio.patrimoine.ui.components.objOrNull
import fr.julesgourio.patrimoine.ui.components.pct
import fr.julesgourio.patrimoine.ui.components.rememberCall
import fr.julesgourio.patrimoine.ui.components.str
import fr.julesgourio.patrimoine.ui.components.strings
import fr.julesgourio.patrimoine.ui.theme.LocalMoney
import fr.julesgourio.patrimoine.ui.theme.Pt
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import org.json.JSONObject
import java.time.YearMonth
import java.time.format.DateTimeFormatter
import java.time.format.TextStyle
import java.util.Locale

/** Écran Flux (maquette docs/maquette, colonne « Revenus et dépenses ») : `depenses_ecran` apporte les opérations, les budgets et `flux_detail`. */

private val MOIS_LONG = DateTimeFormatter.ofPattern("MMMM yyyy", Locale.FRANCE)
private val MOIS_COURT = DateTimeFormatter.ofPattern("MMM yy", Locale.FRANCE)
private val AMBRE = Color(0xFFEDA100)
private val COULEURS_CAT = Pt.Series + listOf(Color(0xFFD55181), Color(0xFF0E8A8A), Color(0xFFC98500), Color(0xFF3B4A6B))
private val COULEUR_SALAIRE = Pt.Series[0]
private val COULEUR_PRIMES = Pt.Series[4]
private val COULEUR_PLACEMENTS = Pt.Series[2]
private val COULEUR_AUTRES = Pt.Series[5]

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

/** Nom du mois seul (« avril »). */
private fun moisNom(m: String): String = try {
    YearMonth.parse(m).month.getDisplayName(TextStyle.FULL, Locale.FRANCE)
} catch (e: Exception) {
    m
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

/** Un mois de `flux_detail.mois` ; montants en euros, [taux] en fraction (null tant que le mois est incomplet). */
private class MoisFlux(
    val mois: String, val revenus: Double, val salaire: Double, val primes: Double, val placements: Double,
    val autres: Double, val depenses: Double, val epargne: Double, val taux: Double?, val investi: Double,
    val chargesFixes: Double, val partiel: Boolean, val vide: Boolean, val remboursements: Double = 0.0,
)

private fun moisFlux(d: JSONObject): List<MoisFlux> = d.objOrNull("flux_detail")?.list("mois").orEmpty().mapNotNull { m ->
    val mois = m.str("mois") ?: return@mapNotNull null
    MoisFlux(mois, m.num("revenus") ?: 0.0, m.num("salaire") ?: 0.0, m.num("primes") ?: 0.0, m.num("placements") ?: 0.0,
        m.num("autres") ?: 0.0, m.num("depenses") ?: 0.0, m.num("epargne") ?: 0.0, m.num("taux"), m.num("investi") ?: 0.0,
        m.num("charges_fixes") ?: 0.0, m.bool("partiel"), m.bool("vide"), m.num("remboursements") ?: 0.0)
}

/** The 13 months ending with the current one, oldest first. */
private fun treizeMois(): List<String> {
    val fin = YearMonth.now()
    return (12 downTo 0).map { fin.minusMonths(it.toLong()).toString() }
}

/** Barres mensuelles empilées par catégorie : les 6 plus grosses sur la période, le reste en « Autres » (toutes si 7 ou moins). */
private fun groupes(ops: List<Op>, mois: List<String>): List<BarGroup> {
    val noms = ops.groupBy { it.categorie }.mapValues { e -> e.value.sumOf { it.montant } }.entries.sortedByDescending { it.value }.map { it.key }
    val gardees = if (noms.size <= 7) noms else noms.take(6)
    return mois.map { m ->
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

/** « 12,5 % » arrondi à l'entier, depuis une fraction. */
private fun pctEntier(x: Double?): String = pct(x, sign = false, digits = 0)

// --- Flux ------------------------------------------------------------------------------------------------------

@Composable
fun DepensesScreen(nav: NavController) {
    val ecran = rememberCall("depenses_ecran", Engine.args("mois" to 13))
    var edit by remember { mutableStateOf<Categorie?>(null) }
    var recat by remember { mutableStateOf<Op?>(null) }
    var erreur by remember { mutableStateOf<String?>(null) }
    var moisSel by rememberSaveable { mutableStateOf(YearMonth.now().toString()) }
    var catSel by remember { mutableStateOf<String?>(null) }
    var jourSel by remember { mutableStateOf<String?>(null) }
    var recherche by remember { mutableStateOf("") }
    val scope = rememberCoroutineScope()

    CallScreen(ecran, PaddingValues(0.dp), horizontal = 0.dp) { d ->
        val ops = operations(d)
        val flux = moisFlux(d)
        val months = flux.map { it.mois }.ifEmpty { treizeMois() }
        val courant = YearMonth.now().toString()
        val idx = months.indexOf(moisSel).let { if (it >= 0) it else months.lastIndex }
        val sel = months[idx]
        val fluxSel = flux.firstOrNull { it.mois == sel }
        val complets = flux.filter { !it.partiel && !it.vide && it.mois != sel }
        val budgets = d.objOrNull("mois_en_cours")
        fun budgetDe(c: String): Double? = budgets?.objOrNull(c)?.num("budget")

        val duMois = ops.filter { it.mois == sel }
        val parCat = duMois.groupBy { it.categorie }.mapValues { e -> e.value.sumOf { it.montant } }
        val cats = (parCat.keys + (if (sel == courant) budgets?.keys()?.asSequence()?.filter { budgetDe(it) != null }?.toList().orEmpty() else emptyList()))
            .distinct().map { Categorie(it, parCat[it] ?: 0.0, if (sel == courant) budgetDe(it) else null) }
            .sortedByDescending { it.depense }
        val ordreCat = ops.groupBy { it.categorie }.mapValues { e -> e.value.sumOf { it.montant } }.entries
            .sortedByDescending { it.value }.map { it.key }
        val couleur: (String) -> Color = { c -> if (c !in ordreCat) Pt.Mute else COULEURS_CAT[ordreCat.indexOf(c) % COULEURS_CAT.size] }
        val moisComplets = complets.map { it.mois }
        fun moyenneCat(c: String): Double =
            if (moisComplets.isEmpty()) 0.0 else ops.filter { it.categorie == c && it.mois in moisComplets }.sumOf { it.montant } / moisComplets.size

        fun changerMois(m: String) { moisSel = m; catSel = null; jourSel = null }

        item {
            EnTete(
                moisLong(sel), peutReculer = idx > 0, peutAvancer = idx < months.lastIndex,
                onReculer = { changerMois(months[idx - 1]) }, onAvancer = { changerMois(months[idx + 1]) },
                onRechercher = { nav.navigate(Routes.OPERATIONS) },
            )
        }
        if (erreur != null) item { Box(Modifier.padding(horizontal = 16.dp)) { Text(erreur.orEmpty(), color = MaterialTheme.colorScheme.error) } }

        // (1) Bloc sombre : revenus, dépenses, épargne du mois et graphique des mois.
        item {
            Box(Modifier.padding(horizontal = 16.dp)) {
                if (fluxSel == null) Carte { Muted("Données de flux indisponibles.") }
                else BlocFlux(flux, fluxSel, complets, idx) { changerMois(flux[it].mois) }
            }
        }

        if (fluxSel != null) {
            val ind = d.objOrNull("flux_detail")?.objOrNull("indicateurs")
            item { Box(Modifier.padding(horizontal = 16.dp)) { CarteRevenus(ind) } }
            if (fluxSel.revenus > 0) item { Box(Modifier.padding(horizontal = 16.dp)) { CarteUtilisation(fluxSel) } }
        }

        // (2) Dépenses du mois par catégorie, écart à la moyenne et budget.
        item {
            Box(Modifier.padding(horizontal = 16.dp)) {
                Carte {
                    CarteEntete("Dépenses", if (moisComplets.isEmpty() || fluxSel?.partiel == true) null else "écart à ta moyenne")
                    if (cats.isEmpty()) Muted("Aucune dépense ce mois-là.")
                    else Muted("${duMois.size} opérations · panier moyen " + euros(duMois.sumOf { it.montant } / maxOf(1, duMois.size), cents = true))
                    val totalCats = cats.sumOf { it.depense }
                    val echelle = maxOf(1.0, cats.maxOfOrNull { maxOf(it.depense, it.budget ?: 0.0) } ?: 1.0)
                    cats.forEach { c ->
                        val av = moyenneCat(c.nom)
                        LigneCategorie(
                            c, couleur(c.nom), echelle, if (totalCats > 0) c.depense / totalCats else null, if (moisComplets.isEmpty() || fluxSel?.partiel == true || av <= 0) null else c.depense - av,
                            choisie = catSel == c.nom,
                            onClick = { catSel = if (catSel == c.nom) null else c.nom },
                            onBudget = { edit = c },
                        )
                    }
                    if ((fluxSel?.remboursements ?: 0.0) > 0.5) Row(Modifier.fillMaxWidth().padding(horizontal = 6.dp, vertical = 4.dp)) {
                        Text("Remboursements", Modifier.weight(1f), fontSize = 13.sp, fontWeight = FontWeight.Medium, color = Pt.Mute)
                        Text("−" + euros(fluxSel!!.remboursements, cents = false), fontSize = 13.sp, fontWeight = FontWeight.SemiBold, color = LocalMoney.current.gain)
                    }
                    if (sel == courant) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        Box(Modifier.width(2.dp).height(12.dp).background(Pt.Encre, RoundedCornerShape(1.dp)))
                        Text("Budget mensuel", fontSize = 12.sp, color = Pt.Mute)
                    }
                    Muted("Touchez une catégorie pour ne voir que ses opérations ; le crayon fixe un budget mensuel.")
                }
            }
        }

        // (2 bis) Dépenses des 13 mois par catégorie : toucher une barre change de mois et détaille ses catégories.
        item {
            Box(Modifier.padding(horizontal = 16.dp)) {
                Carte {
                    val moyenne = if (moisComplets.isEmpty()) 0.0 else moisComplets.sumOf { m -> ops.filter { it.mois == m }.sumOf { it.montant } } / moisComplets.size
                    CarteEntete("Dépenses par mois", "${months.size} mois")
                    StackedBarChart(
                        groupes(ops, months), selectedKey = sel, limitLine = moyenne.takeIf { it > 0 },
                        valueFormat = { euros(it, cents = false) }, couleur = couleur,
                        onGroupClick = { g -> g.key?.let { changerMois(it) } },
                    )
                    Muted("Touchez une barre pour le détail du mois et pour y aller. Ligne = moyenne des mois complets.")
                }
            }
        }

        // (3) Taux d'épargne.
        if (flux.any { it.taux != null }) {
            item { Box(Modifier.padding(horizontal = 16.dp)) { CarteTaux(flux, sel, d.objOrNull("flux_detail")?.objOrNull("indicateurs")?.num("taux_moyen_12m")) } }
        }

        // (4) Prélèvements attendus ce mois-ci.
        val aVenir = d.objOrNull("flux_detail")?.list("a_venir").orEmpty()
        if (sel == courant && aVenir.isNotEmpty()) {
            item { Box(Modifier.padding(horizontal = 16.dp)) { CarteAVenir(aVenir, d.objOrNull("flux_detail")?.num("a_venir_total")) } }
        }

        // (5) Calendrier du mois.
        item {
            Box(Modifier.padding(horizontal = 16.dp)) {
                Carte {
                    CarteEntete("Calendrier", "jour par jour")
                    val premierJour = YearMonth.parse(sel).atDay(1)
                    val nbJours = YearMonth.parse(sel).lengthOfMonth()
                    val decalage = premierJour.dayOfWeek.value - 1
                    val parJour = duMois.filter { catSel == null || it.categorie == catSel }.groupBy { it.date }
                        .mapValues { e -> e.value.sumOf { it.montant } }
                    val maxJour = maxOf(1.0, parJour.values.maxOrNull() ?: 0.0)
                    Row(Modifier.fillMaxWidth()) {
                        listOf("L", "M", "M", "J", "V", "S", "D").forEach {
                            Text(it, Modifier.weight(1f), textAlign = TextAlign.Center, fontSize = 11.sp, fontWeight = FontWeight.Medium, color = Pt.Mute)
                        }
                    }
                    val cases: List<Int?> = List(decalage) { null } + (1..nbJours).toList()
                    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        cases.chunked(7).forEach { semaine ->
                            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                                (semaine + List(7 - semaine.size) { null }).forEach { n ->
                                    if (n == null) Spacer(Modifier.weight(1f))
                                    else {
                                        val iso = "$sel-${n.toString().padStart(2, '0')}"
                                        val v = parJour[iso] ?: 0.0
                                        val alpha = if (v > 0) 0.18f + 0.82f * minOf(1.0, v / maxJour).toFloat() else 0f
                                        val choisi = jourSel == iso
                                        Box(
                                            Modifier.weight(1f).aspectRatio(1f).clip(RoundedCornerShape(8.dp))
                                                .background(Pt.Pastille)
                                                .background(Pt.Encre.copy(alpha = alpha))
                                                .let { if (choisi) it.border(2.dp, Pt.Accent, RoundedCornerShape(8.dp)) else it }
                                                .clickable { jourSel = if (choisi) null else iso },
                                            contentAlignment = Alignment.Center,
                                        ) { Text(n.toString(), fontSize = 11.sp, fontWeight = FontWeight.Medium, color = if (alpha > 0.55f) Color.White else Pt.Encre) }
                                    }
                                }
                            }
                        }
                    }
                    Muted("Plus la case est foncée, plus la dépense du jour est forte. Touchez un jour pour ne voir que ses dépenses.")
                }
            }
        }

        // (6) Opérations du mois, filtrées.
        item {
            Box(Modifier.padding(horizontal = 16.dp)) {
                Carte {
                    CarteEntete("Opérations", droite = {
                        Text("Tout voir", fontSize = 13.sp, fontWeight = FontWeight.SemiBold, color = Pt.Accent,
                            modifier = Modifier.clickable { nav.navigate(Routes.OPERATIONS) })
                    })
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
                    Column {
                        liste.take(30).forEachIndexed { i, o ->
                            LigneListe(
                                initiales(o.commercant), couleur(o.categorie), o.commercant,
                                o.categorie + " · " + dateCourte(o.date) + if (o.modifiee) " · modifiée" else "",
                                euros(-o.montant, sign = true, cents = true),
                                separateur = i > 0, onClick = { recat = o },
                            )
                        }
                    }
                    if (liste.size > 30) Muted("${liste.size - 30} autres opérations : affinez avec la recherche ou un filtre.")
                    Muted("Touchez une opération pour changer sa catégorie.")
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

// --- Composants de l'écran ---------------------------------------------------------------------------------------

@Composable
private fun EnTete(
    mois: String, peutReculer: Boolean, peutAvancer: Boolean, onReculer: () -> Unit, onAvancer: () -> Unit, onRechercher: () -> Unit,
) {
    Row(
        Modifier.fillMaxWidth().windowInsetsPadding(WindowInsets.statusBars).padding(horizontal = 16.dp).height(44.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text("Flux", Modifier.weight(1f), fontSize = 26.sp, fontWeight = FontWeight.Bold, letterSpacing = (-0.5).sp, color = Pt.Encre)
        Box(Modifier.size(40.dp).clip(CircleShape).background(Pt.Carte).clickable(onClick = onRechercher), contentAlignment = Alignment.Center) {
            Icon(Icons.Filled.Search, contentDescription = "Rechercher dans les opérations", Modifier.size(20.dp), tint = Pt.Encre)
        }
        Spacer(Modifier.width(6.dp))
        Row(Modifier.height(40.dp).clip(RoundedCornerShape(20.dp)).background(Pt.Carte), verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(36.dp).clickable(enabled = peutReculer, onClick = onReculer), contentAlignment = Alignment.Center) {
                Text("‹", fontSize = 20.sp, fontWeight = FontWeight.SemiBold, color = if (peutReculer) Pt.Encre else Pt.Encre.copy(alpha = 0.3f))
            }
            Text(mois, fontSize = 13.sp, fontWeight = FontWeight.SemiBold, color = Pt.Encre, maxLines = 1)
            Box(Modifier.size(36.dp).clickable(enabled = peutAvancer, onClick = onAvancer), contentAlignment = Alignment.Center) {
                Text("›", fontSize = 20.sp, fontWeight = FontWeight.SemiBold, color = if (peutAvancer) Pt.Encre else Pt.Encre.copy(alpha = 0.3f))
            }
        }
    }
}

/** Un chiffre du bandeau sombre : libellé, valeur, mention colorée dessous. */
@Composable
private fun Chiffre(modifier: Modifier, libelle: String, valeur: String, mention: String, teinteValeur: Color, teinteMention: Color) {
    Column(modifier, verticalArrangement = Arrangement.spacedBy(2.dp)) {
        Text(libelle, fontSize = 12.sp, fontWeight = FontWeight.Medium, color = Pt.NuitSub)
        Text(valeur, fontSize = 20.sp, fontWeight = FontWeight.Bold, color = teinteValeur, maxLines = 1)
        Text(mention, fontSize = 12.sp, fontWeight = FontWeight.Medium, color = teinteMention, maxLines = 1)
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun BlocFlux(flux: List<MoisFlux>, m: MoisFlux, autres: List<MoisFlux>, idx: Int, onChoix: (Int) -> Unit) {
    val money = LocalMoney.current
    val moyRev = autres.takeIf { it.isNotEmpty() }?.map { it.revenus }?.average()
    val moyDep = autres.takeIf { it.isNotEmpty() }?.map { it.depenses }?.average()
    fun ecart(v: Double, moy: Double?) = if (moy == null || moy <= 0) null else (v - moy) / moy
    val eRev = if (m.partiel) null else ecart(m.revenus, moyRev)
    val eDep = if (m.partiel) null else ecart(m.depenses, moyDep)
    val barres = flux.map { f ->
        val lettre = try { YearMonth.parse(f.mois).month.getDisplayName(TextStyle.SHORT, Locale.FRANCE).take(1).uppercase() } catch (e: Exception) { "" }
        val sources = listOf(
            Triple("Salaire", COULEUR_SALAIRE, f.salaire), Triple("Primes", COULEUR_PRIMES, f.primes),
            Triple("Dividendes, intérêts", COULEUR_PLACEMENTS, f.placements), Triple("Autres", COULEUR_AUTRES, f.autres),
        )
        val detail = buildList {
            add(LigneInfobulle(moisLong(f.mois) + if (f.partiel) " · en cours" else "", null, gras = true))
            add(LigneInfobulle("Revenus", euros(f.revenus, cents = false), gras = true))
            sources.filter { it.third > 0.5 }.forEach { (nom, c, v) -> add(LigneInfobulle(nom, euros(v, cents = false), c)) }
            add(LigneInfobulle("Dépenses", euros(f.depenses, cents = false), CouleurDepenses, gras = true))
            add(LigneInfobulle("Épargne", euros(f.epargne, sign = true, cents = false), teinte = if (f.epargne >= 0) money.gain else money.loss, gras = true))
            add(LigneInfobulle("Taux d'épargne", if (f.taux != null) pctEntier(f.taux) else "—"))
        }
        BarreFlux(lettre, sources.map { it.second to it.third }, f.depenses, f.epargne, detail)
    }
    Column(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(24.dp)).background(Pt.Nuit).padding(top = 18.dp, bottom = 14.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Row(Modifier.fillMaxWidth().padding(horizontal = 18.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Chiffre(Modifier.weight(1f), "Revenus", euros(m.revenus, cents = false), if (m.partiel) "mois en cours" else if (eRev == null) "—" else pct(eRev, digits = 0) + " vs moy.", Color.White,
                if (eRev == null) Pt.NuitSub else if (eRev >= 0) money.gainNight else money.lossNight)
            Chiffre(Modifier.weight(1f), "Dépenses", euros(m.depenses, cents = false), if (m.partiel) "mois en cours" else if (eDep == null) "—" else pct(eDep, digits = 0) + " vs moy.", Color.White,
                if (eDep == null) Pt.NuitSub else if (eDep <= 0) money.gainNight else money.lossNight)
            Chiffre(Modifier.weight(1f), "Épargne", euros(m.epargne, cents = false), if (m.taux != null) "taux " + pctEntier(m.taux) else "mois en cours",
                if (m.epargne >= 0) money.gainNight else money.lossNight, Pt.NuitSub)
        }
        Box(Modifier.padding(horizontal = 12.dp)) { GraphiqueFlux(barres, idx, onChoix) }
        FlowRow(
            Modifier.fillMaxWidth().padding(horizontal = 18.dp),
            horizontalArrangement = Arrangement.spacedBy(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            listOf("Salaire" to COULEUR_SALAIRE, "Primes" to COULEUR_PRIMES, "Dividendes, intérêts" to COULEUR_PLACEMENTS, "Autres" to COULEUR_AUTRES,
                "Dépenses" to CouleurDepenses, "Épargne nette" to Color.White).forEach { (nom, c) ->
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.size(8.dp).clip(RoundedCornerShape(2.dp)).background(c))
                    Text(nom, fontSize = 12.sp, color = Pt.NuitSub, maxLines = 1)
                }
            }
        }
    }
}

@Composable
private fun CarteRevenus(ind: JSONObject?) {
    val sources = ind?.objOrNull("revenus_par_source_12m")
    val total = ind?.num("revenus_12m") ?: 0.0
    val lignes = listOf(
        Triple("Salaire", COULEUR_SALAIRE, sources?.num("salaire") ?: 0.0),
        Triple("Primes", COULEUR_PRIMES, sources?.num("primes") ?: 0.0),
        Triple("Dividendes et intérêts", COULEUR_PLACEMENTS, sources?.num("placements") ?: 0.0),
        Triple("Autres", COULEUR_AUTRES, sources?.num("autres") ?: 0.0),
    ).filter { it.third > 0 }
    val maxi = lignes.maxOfOrNull { it.third } ?: 1.0
    val nb = ind?.num("mois_comptes")?.toInt() ?: 0
    val salaire = ind?.objOrNull("salaire")
    val evolSalaire = salaire?.num("evolution")
    Carte {
        CarteEntete("Revenus", if (nb > 0) "$nb mois · ${euros(total, cents = false)}" else null)
        if (nb == 0) Muted("Pas encore un mois complet de données.")
        lignes.forEach { (nom, c, v) ->
            Column(verticalArrangement = Arrangement.spacedBy(5.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Box(Modifier.size(8.dp).clip(RoundedCornerShape(3.dp)).background(c))
                    Text(nom, Modifier.weight(1f), fontSize = 13.sp, fontWeight = FontWeight.Medium, color = Pt.Encre, maxLines = 1)
                    Text(euros(v, cents = false), fontSize = 13.sp, fontWeight = FontWeight.SemiBold, color = Pt.Encre)
                    Text(pctEntier(v / total), Modifier.widthIn(min = 40.dp), fontSize = 13.sp, color = Pt.Mute, textAlign = TextAlign.End)
                }
                Piste(v / maxi, c)
            }
        }
        GrilleIndicateurs(
            listOf(
                Indicateur("Moyenne sur 12 mois", euros(ind?.num("revenus_moyens"), cents = false), "par mois"),
                Indicateur("Évolution sur 1 an", ind?.num("evolution_1an")?.let { pct(it) } ?: "—", "vs 12 mois précédents", ton = ind?.num("evolution_1an")),
                Indicateur("Salaire", euros(salaire?.num("montant"), cents = false),
                    if (evolSalaire != null) pct(evolSalaire) + " depuis " + moisNom(salaire.str("depuis") ?: "") else "dernier versement"),
                Indicateur("Revenus de placements", euros(ind?.num("placements_12m"), cents = false),
                    "sur 12 mois · " + euros((ind?.num("placements_12m") ?: 0.0) / 12, cents = false) + " par mois"),
            ),
        )
    }
}

/** « Où vont tes revenus » : charges fixes, dépenses courantes, investi, mis de côté, sur le mois choisi. */
@Composable
private fun CarteUtilisation(m: MoisFlux) {
    val reste = (m.revenus - m.depenses).coerceAtLeast(0.0)
    val investi = minOf(m.investi, reste)
    val parts = listOf(
        Triple("Charges fixes", Pt.Encre, m.chargesFixes),
        Triple("Dépenses courantes", CouleurDepenses, (m.depenses - m.chargesFixes).coerceAtLeast(0.0)),
        Triple("Investi", Pt.Series[0], investi),
        Triple("Mis de côté", Pt.Series[2], reste - investi),
    )
    val base = maxOf(m.revenus, parts.sumOf { it.third })
    Carte {
        CarteEntete("Où vont tes revenus", euros(m.revenus, cents = false))
        BarreRepartition(parts.map { it.third to it.second })
        parts.forEach { (nom, c, v) -> LigneRepartition(c, nom, euros(v, cents = false), pctEntier(v / base)) }
        if (m.partiel) Muted("Mois en cours : les chiffres bougent encore.")
    }
}

/** Piste de progression ; [repere] (0..1) pose le trait du budget. */
@Composable
private fun Piste(ratio: Double, couleur: Color, repere: Double? = null) {
    BoxWithConstraints(Modifier.fillMaxWidth().height(12.dp)) {
        Box(Modifier.fillMaxWidth().height(8.dp).align(Alignment.Center).clip(RoundedCornerShape(4.dp)).background(Pt.Ligne)) {
            Box(Modifier.fillMaxWidth(ratio.toFloat().coerceIn(0f, 1f)).fillMaxHeight().background(couleur))
        }
        if (repere != null) Box(
            Modifier.offset(x = maxWidth * repere.toFloat().coerceIn(0f, 1f) - 1.dp).width(2.dp).height(12.dp)
                .background(Pt.Encre, RoundedCornerShape(1.dp)),
        )
    }
}

@Composable
private fun LigneCategorie(
    c: Categorie, couleur: Color, echelle: Double, part: Double?, ecart: Double?, choisie: Boolean, onClick: () -> Unit, onBudget: () -> Unit,
) {
    val money = LocalMoney.current
    val b = c.budget?.takeIf { it > 0 }
    val depasse = b != null && c.depense > b
    val barre = when {
        depasse -> money.loss
        b != null && c.depense / b > 0.8 -> AMBRE
        else -> couleur
    }
    Column(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).clickable(onClick = onClick)
            .let { if (choisie) it.border(1.dp, Pt.Encre, RoundedCornerShape(10.dp)) else it }
            .padding(horizontal = 6.dp, vertical = 4.dp),
        verticalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Box(Modifier.size(8.dp).clip(RoundedCornerShape(3.dp)).background(couleur))
            Text(c.nom, Modifier.weight(1f), fontSize = 13.sp, fontWeight = FontWeight.Medium, color = Pt.Encre, maxLines = 1, overflow = TextOverflow.Ellipsis)
            if (ecart != null) Text(
                if (kotlin.math.abs(ecart) < 0.5) "=" else euros(ecart, sign = true, cents = false), fontSize = 12.sp, fontWeight = FontWeight.SemiBold,
                color = if (ecart > 0.5) money.loss else if (ecart < -0.5) money.gain else Pt.Mute,
            )
            Text(euros(c.depense, cents = false), fontSize = 13.sp, fontWeight = FontWeight.SemiBold, color = if (depasse) money.loss else Pt.Encre)
            if (part != null) Text(pctEntier(part), Modifier.widthIn(min = 34.dp), fontSize = 12.sp, color = Pt.Mute, textAlign = TextAlign.End)
            Box(Modifier.size(28.dp).clip(CircleShape).clickable(onClick = onBudget), contentAlignment = Alignment.Center) {
                Icon(Icons.Filled.Edit, contentDescription = "Budget : ${c.nom}", Modifier.size(14.dp), tint = Pt.Mute)
            }
        }
        Piste(c.depense / echelle, barre, b?.let { it / echelle })
        if (b != null) Text(
            "budget " + euros(b, cents = false) + if (depasse) " · dépassé" else "", fontSize = 12.sp,
            color = if (depasse) money.loss else Pt.Mute,
        )
    }
}

@Composable
private fun CarteTaux(flux: List<MoisFlux>, sel: String, tauxMoyen: Double?) {
    val taux = flux.map { it.taux }
    val valides = flux.filter { it.taux != null && it.mois <= sel }
    val dernier = valides.lastOrNull() ?: flux.last { it.taux != null }
    val moyenne = tauxMoyen ?: taux.filterNotNull().average()
    Carte {
        CarteEntete("Taux d'épargne", "${flux.size} mois")
        Row(verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(pctEntier(dernier.taux), fontSize = 26.sp, fontWeight = FontWeight.Bold, color = Pt.Encre)
            Text("moyenne 12 mois ${pctEntier(moyenne)}", Modifier.padding(bottom = 4.dp), fontSize = 13.sp, color = Pt.Mute)
        }
        CourbeTaux(taux, moisCourt(dernier.mois)) { i ->
            val f = flux[i]
            listOf(
                LigneInfobulle(moisLong(f.mois), null, gras = true),
                LigneInfobulle("Revenus", euros(f.revenus, cents = false)),
                LigneInfobulle("Dépenses", euros(f.depenses, cents = false)),
                LigneInfobulle("Épargne", euros(f.epargne, sign = true, cents = false) + " · " + pctEntier(f.taux), gras = true),
            )
        }
        Muted("Dépenses nettes des remboursements ; héritages et donations à part. Le mois en cours est exclu tant qu'il n'est pas fini.")
    }
}

@Composable
private fun CarteAVenir(items: List<JSONObject>, total: Double?) {
    Carte {
        CarteEntete("À venir ce mois", euros(total, cents = true))
        Column {
            items.forEachIndexed { i, o ->
                val jours = o.num("dans_jours")?.toInt() ?: 0
                val quand = when (jours) { 0 -> "aujourd'hui"; 1 -> "demain"; else -> "dans $jours jours" }
                LigneListe(
                    o.str("date")?.takeLast(2)?.trimStart('0').orEmpty(), Pt.Sub, o.str("commercant") ?: "—", "$quand · mensuel",
                    euros(-(o.num("montant") ?: 0.0), cents = true), separateur = i > 0,
                )
            }
        }
        Muted("Prélèvements récurrents repérés dans tes opérations, pas encore passés ce mois-ci.")
    }
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
    var vendeur by remember { mutableStateOf<String?>(null) }
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
                                label = o.str("commercant") ?: o.str("counterparty") ?: o.str("label") ?: "—",
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
        val nomVendeur = op.str("commercant") ?: commercant
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
                    if (nomVendeur != null) {
                        TextButton(onClick = { vendeur = nomVendeur; cible = null }) { Text("Renommer ce vendeur") }
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

    vendeur?.let { nom ->
        RenameVendorDialog(
            raw = nom,
            nomActuel = nom,
            pasAbonnement = false,
            onDismiss = { vendeur = null },
            onDone = { vendeur = null; erreur = null; state.reload() },
        )
    }
}
