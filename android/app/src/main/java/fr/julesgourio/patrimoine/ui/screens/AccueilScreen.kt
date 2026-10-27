package fr.julesgourio.patrimoine.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Sync
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.navigation.NavController
import fr.julesgourio.patrimoine.ui.Routes
import fr.julesgourio.patrimoine.ui.components.BigFigure
import fr.julesgourio.patrimoine.ui.components.CallScreen
import fr.julesgourio.patrimoine.ui.components.ChartSeries
import fr.julesgourio.patrimoine.ui.components.DonutChart
import fr.julesgourio.patrimoine.ui.components.InfoRow
import fr.julesgourio.patrimoine.ui.components.InteractiveLineChart
import fr.julesgourio.patrimoine.ui.components.LocalSync
import fr.julesgourio.patrimoine.ui.components.Muted
import fr.julesgourio.patrimoine.ui.components.ScreenScaffold
import fr.julesgourio.patrimoine.ui.components.SectionCard
import fr.julesgourio.patrimoine.ui.components.Slice
import fr.julesgourio.patrimoine.ui.components.chartPalette
import fr.julesgourio.patrimoine.ui.components.day
import fr.julesgourio.patrimoine.ui.components.euros
import fr.julesgourio.patrimoine.ui.components.gainColor
import fr.julesgourio.patrimoine.ui.components.int
import fr.julesgourio.patrimoine.ui.components.list
import fr.julesgourio.patrimoine.ui.components.moment
import fr.julesgourio.patrimoine.ui.components.num
import fr.julesgourio.patrimoine.ui.components.objOrNull
import fr.julesgourio.patrimoine.ui.components.pct
import fr.julesgourio.patrimoine.ui.components.rememberCall
import fr.julesgourio.patrimoine.ui.components.str
import fr.julesgourio.patrimoine.ui.components.strings
import org.json.JSONArray
import java.time.LocalDate

private val PERIODS: List<Pair<String, Int?>> =
    listOf("1 M" to 30, "6 M" to 182, "1 A" to 365, "5 A" to 1826, "Tout" to null)
private val MODES = listOf("Total" to "tot", "Par compte (empilé)" to "cpt", "Sans le PEG" to "nopeg")
private const val MINUS = "−"

@Composable
fun AccueilScreen(nav: NavController) {
    val sync = LocalSync.current
    val state = rememberCall("accueil")
    // Au niveau de l'écran : la période et le mode de la courbe survivent à la sortie de la carte de l'écran.
    var days by rememberSaveable { mutableStateOf<Int?>(365) }
    var mode by rememberSaveable { mutableStateOf("tot") }
    ScreenScaffold(
        "Patrimoine",
        actions = {
            IconButton(onClick = sync.start, enabled = !sync.running) {
                Icon(Icons.Filled.Sync, contentDescription = "Synchroniser")
            }
        },
    ) { padding ->
        CallScreen(state, padding) { data ->
            val p = data.objOrNull("patrimoine")
            val total = p?.num("total")
            if (p == null || total == null) {
                item { Welcome(onSettings = { nav.navigate(Routes.REGLAGES) }, onSync = sync.start) }
                return@CallScreen
            }
            val totalCurve = curve(data.optJSONArray("courbe"))
            val syn = data.objOrNull("synthese")?.takeIf { it.str("erreur") == null }
            val accountRows = syn?.list("comptes").orEmpty()
            val accountColors = chartPalette(accountRows.size)
            val colorOf = accountRows.mapIndexed { i, c -> (c.str("compte") ?: "") to accountColors[i] }.toMap()
            item {
                val byAccount = remember(data) {
                    data.objOrNull("courbes_comptes")?.let { o ->
                        o.keys().asSequence().map { it to curve(o.optJSONArray(it)) }
                            .filter { it.second.isNotEmpty() }.toList()
                    } ?: emptyList()
                }
                val peg = byAccount.firstOrNull { it.first == "PEG Airbus" }?.second.orEmpty().toMap()
                val view = remember(totalCurve, byAccount, days, mode) {
                    // « Sans le PEG » = total moins la courbe du compte PEG Airbus, comme la maquette.
                    val base = if (mode == "nopeg") totalCurve.map { it.first to it.second - (peg[it.first] ?: 0.0) } else totalCurve
                    val shown = cut(base, days)
                    val series = if (mode == "cpt") {
                        byAccount.map { (name, pts) -> ChartSeries(name, cut(pts, days), color = colorOf[name]) }
                            .filter { it.points.isNotEmpty() }
                    } else listOf(ChartSeries("Total", shown))
                    Triple(base, shown, series)
                }
                val cur = view.first.lastOrNull()?.second ?: total
                val period = if (view.second.size >= 2) cur - view.second.first().second else null
                val month = ago(view.first, 30)?.let { cur - it }
                SectionCard {
                    BigFigure(
                        caption = if (mode == "nopeg") "Patrimoine hors PEG Airbus · avant impôts" else "Patrimoine total · avant impôts", value = euros(cur),
                    )
                    Text(
                        buildAnnotatedString {
                            withStyle(SpanStyle(color = gainColor(period))) { append(euros(period, sign = true)) }
                            append(" sur la période · ")
                            withStyle(SpanStyle(color = gainColor(month))) { append(euros(month, sign = true)) }
                            append(" sur 30 j")
                        },
                        style = MaterialTheme.typography.bodyMedium,
                    )
                    Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        PERIODS.forEach { (label, d) ->
                            FilterChip(selected = days == d, onClick = { days = d }, label = { Text(label) })
                        }
                    }
                    InteractiveLineChart(view.third, showPeriods = false, showChange = false, stacked = mode == "cpt")
                    Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        MODES.forEach { (label, m) ->
                            FilterChip(selected = mode == m, onClick = { mode = m }, label = { Text(label, maxLines = 1) })
                        }
                    }
                }
            }
            if (syn != null) {
                item {
                    val peaNote = syn.str("pea_ouverture")?.takeIf { it.isNotBlank() && syn.has("pea_5_ans") }?.let {
                        " Le PEA a été ouvert le ${day(it)} : " + if (syn.optBoolean("pea_5_ans")) "plus de 5 ans, régime plein."
                        else "moins de 5 ans, un retrait aujourd'hui serait en fait taxé à 30 % comme le compte-titres."
                    }.orEmpty()
                    val kpis = listOf(
                        Kpi("Après impôts si tout était vendu", euros(syn.num("apres_impots")),
                            "$MINUS${euros(syn.num("impots_latents"))} d'impôts latents", null,
                            "Patrimoine total moins l'impôt estimé sur tes gains si tu vendais et retirais tout aujourd'hui : " +
                                "30 % sur le compte-titres, les dividendes hors PEA et les intérêts ; 17,2 % de prélèvements " +
                                "sociaux sur le PEA et le PEG. Les versements ne sont pas imposés." + peaNote),
                        Kpi("Depuis le 1er janvier", euros(syn.num("depuis_1er_janvier"), sign = true),
                            pct(syn.num("depuis_1er_janvier_pct")) + " · inclut ce que tu as épargné",
                            syn.num("depuis_1er_janvier"),
                            "Variation de ton patrimoine total : elle mélange les gains de marché et l'argent que tu as versé " +
                                "ou reçu (salaire épargné, héritage…). Pour les gains purs, voir « Gains d'investissement »."),
                        Kpi("Sur 1 an", euros(syn.num("sur_1_an"), sign = true), "même remarque : inclut l'épargne",
                            syn.num("sur_1_an"), "Même calcul sur 12 mois glissants."),
                        Kpi("Épargne moyenne", euros(syn.num("epargne_moyenne")) + " / mois",
                            pct(syn.num("epargne_pct_revenus"), sign = false, digits = 0) + " des revenus", null,
                            "Revenus moins dépenses, moyenne des 12 derniers mois complets. Héritages et donations exclus : " +
                                "ils comptent dans le patrimoine, pas dans l'épargne."),
                        Kpi("Part investie en actions", pct(syn.num("part_investie"), sign = false, digits = 0),
                            euros(syn.num("investi")), null,
                            "Compte-titres, PEA et PEG Airbus, en part du patrimoine total."),
                        Kpi("Gains d'investissement (brut)", euros(syn.num("gains_bruts"), sign = true),
                            "dont ${euros(syn.num("interets_et_dividendes"))} d'intérêts et dividendes", syn.num("gains_bruts"),
                            "Avant impôt. Plus-values latentes et réalisées sur les actions (compte-titres, PEA, PEG Airbus) " +
                                "et intérêts et dividendes perçus, depuis le début."),
                        Kpi("Gains d'investissement (net d'impôt estimé)", euros(syn.num("gains_nets"), sign = true),
                            "$MINUS${euros(syn.num("impots_latents"))} de fiscalité", syn.num("gains_nets"),
                            "Estimation à la sortie, au régime de chaque enveloppe (PFU 30 % ou prélèvements sociaux 17,2 %)." + peaNote),
                    )
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        kpis.chunked(2).forEach { pair ->
                            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                pair.forEach { KpiCard(it, Modifier.weight(1f)) }
                                if (pair.size == 1) Spacer(Modifier.weight(1f))
                            }
                        }
                    }
                }
                item {
                    val securities = data.strings("comptes_titres").toSet()
                    val sumTotal = syn.num("total") ?: total
                    SectionCard("Comptes") {
                        Row(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.CenterVertically) {
                            DonutChart(
                                slices = accountRows.mapNotNull { c ->
                                    val name = c.str("compte") ?: return@mapNotNull null
                                    Slice(name, c.num("valeur") ?: 0.0, key = name, color = colorOf[name])
                                },
                                centerTitle = "Total",
                                centerValue = euros(sumTotal),
                                modifier = Modifier.width(130.dp),
                                size = 130.dp,
                                onSliceClick = { s -> if (s.label in securities) nav.navigate(Routes.PORTEFEUILLE) },
                                showLegend = false,
                            )
                            Text("Touche un compte pour voir son détail (lignes, historique).",
                                Modifier.weight(1f), style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                        accountRows.forEach { c ->
                            val name = c.str("compte") ?: return@forEach
                            val value = c.num("valeur")
                            val v30 = c.num("var_30j")
                            Row(
                                Modifier.fillMaxWidth()
                                    .let { if (name in securities) it.clickable { nav.navigate(Routes.PORTEFEUILLE) } else it }
                                    .padding(vertical = 4.dp),
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.spacedBy(10.dp),
                            ) {
                                Box(Modifier.size(9.dp).clip(RoundedCornerShape(3.dp)).background(colorOf[name] ?: Color.Gray))
                                Column(Modifier.weight(1f)) {
                                    Text(name, style = MaterialTheme.typography.bodyLarge)
                                    Muted((c.str("groupe") ?: "") + " · " +
                                        pct(if (sumTotal != 0.0 && value != null) value / sumTotal else null, sign = false, digits = 0))
                                }
                                Column(horizontalAlignment = Alignment.End) {
                                    Text(euros(value), style = MaterialTheme.typography.bodyLarge)
                                    Text(euros(v30, sign = true) + " sur 30 j", style = MaterialTheme.typography.bodySmall,
                                        color = gainColor(v30))
                                }
                            }
                        }
                        Row(Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
                            Text("Total", Modifier.weight(1f), style = MaterialTheme.typography.bodyLarge,
                                fontWeight = FontWeight.Bold)
                            Text(euros(sumTotal), style = MaterialTheme.typography.bodyLarge, fontWeight = FontWeight.Bold)
                        }
                    }
                }
            }
            data.objOrNull("derniere_analyse")?.let { a ->
                item {
                    SectionCard("Dernière analyse", onClick = { a.int("id")?.let { nav.navigate(Routes.analyse(it)) } }) {
                        Text(a.str("titre") ?: "Analyse", style = MaterialTheme.typography.titleSmall,
                            fontWeight = FontWeight.SemiBold)
                        a.strings("points_cles").forEach { Text("• $it", style = MaterialTheme.typography.bodyMedium) }
                        Muted("Séance du " + day(a.str("seance")))
                    }
                }
            }
            val orders = data.int("ordres_proposes") ?: 0
            val alerts = data.int("alertes_30j") ?: 0
            if (orders > 0 || alerts > 0) {
                item {
                    SectionCard("À regarder") {
                        if (orders > 0) {
                            InfoRow("Ordres préparés", "$orders", sub = "À passer toi-même dans Trade Republic",
                                onClick = { nav.navigate(Routes.ORDRES) })
                        }
                        if (alerts > 0) {
                            InfoRow("Alertes (30 jours)", "$alerts", onClick = { nav.navigate(Routes.ALERTES) })
                        }
                    }
                }
            }
            item {
                val last = p.objOrNull("derniere_synchro")
                SectionCard("Synchronisation") {
                    InfoRow("Dernière", moment(last?.str("at")))
                    sync.lastError?.let { Text(it, color = MaterialTheme.colorScheme.error) }
                    val lines = sync.lastLines?.lines() ?: last?.optJSONArray("summary")?.let { a ->
                        (0 until a.length()).map { a.optString(it) }
                    } ?: emptyList()
                    lines.filter { it.isNotBlank() }.forEach { Muted(it) }
                }
            }
        }
    }
}

private fun curve(a: JSONArray?): List<Pair<String, Double>> {
    if (a == null) return emptyList()
    return (0 until a.length()).mapNotNull { i ->
        val p = a.optJSONArray(i) ?: return@mapNotNull null
        p.optString(0) to p.optDouble(1)
    }.filter { !it.second.isNaN() }
}

private fun lastDate(points: List<Pair<String, Double>>): LocalDate? =
    points.lastOrNull()?.first?.let { runCatching { LocalDate.parse(it.take(10)) }.getOrNull() }

/** Points from (last date - [days]) onward; everything when [days] is null. */
private fun cut(points: List<Pair<String, Double>>, days: Int?): List<Pair<String, Double>> {
    if (days == null) return points
    val from = (lastDate(points) ?: return points).minusDays(days.toLong())
    return points.filter { p -> runCatching { !LocalDate.parse(p.first.take(10)).isBefore(from) }.getOrDefault(false) }
}

/** Value of the curve [days] before its last point (last point on or before that date); null if the curve starts later. */
private fun ago(points: List<Pair<String, Double>>, days: Int): Double? {
    val limit = (lastDate(points) ?: return null).minusDays(days.toLong())
    return points.lastOrNull { p -> runCatching { !LocalDate.parse(p.first.take(10)).isAfter(limit) }.getOrDefault(false) }?.second
}

private class Kpi(val label: String, val value: String, val sub: String, val tone: Double?, val help: String)

/** Indicator tile; a touch unfolds its explanation (ⓘ). */
@Composable
private fun KpiCard(k: Kpi, modifier: Modifier = Modifier) {
    var open by remember { mutableStateOf(false) }
    Card(
        modifier = modifier.clickable { open = !open },
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLow),
    ) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(k.label + " ⓘ", style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant)
            Text(k.value, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.SemiBold,
                color = if (k.tone != null) gainColor(k.tone) else MaterialTheme.colorScheme.onSurface)
            Text(k.sub, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            if (open) Text(k.help, Modifier.padding(top = 6.dp), style = MaterialTheme.typography.bodySmall)
        }
    }
}

@Composable
private fun Welcome(onSettings: () -> Unit, onSync: () -> Unit) {
    SectionCard("Bienvenue") {
        Text("La base du téléphone est encore vide.")
        Text("Le plus simple : copie le fichier data/patrimoine.db du PC sur le téléphone, puis Réglages → " +
            "« Importer une base ». Tout l'historique (CMB depuis 2016, PEG, 13F, élus) arrive d'un coup.")
        Text("Sinon : renseigne Trade Republic et la CMB dans les Réglages, puis synchronise.")
        Button(onClick = onSettings) { Text("Ouvrir les réglages") }
        Button(onClick = onSync) { Text("Synchroniser") }
    }
}
