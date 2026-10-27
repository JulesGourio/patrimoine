package fr.julesgourio.patrimoine.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Sync
import androidx.compose.material3.Button
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
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
import fr.julesgourio.patrimoine.ui.components.Sparkline
import fr.julesgourio.patrimoine.ui.components.day
import fr.julesgourio.patrimoine.ui.components.euros
import fr.julesgourio.patrimoine.ui.components.int
import fr.julesgourio.patrimoine.ui.components.moment
import fr.julesgourio.patrimoine.ui.components.num
import fr.julesgourio.patrimoine.ui.components.numbers
import fr.julesgourio.patrimoine.ui.components.objOrNull
import fr.julesgourio.patrimoine.ui.components.pct
import fr.julesgourio.patrimoine.ui.components.rememberCall
import fr.julesgourio.patrimoine.ui.components.str
import fr.julesgourio.patrimoine.ui.components.strings
import org.json.JSONArray
import java.time.LocalDate

@Composable
fun AccueilScreen(nav: NavController) {
    val sync = LocalSync.current
    val state = rememberCall("accueil")
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
            item {
                val v30 = p.num("variation_30j")
                val v1y = p.num("variation_1an")
                var perAccount by remember { mutableStateOf(false) }
                val byAccount = data.objOrNull("courbes_comptes")?.let { o ->
                    o.keys().asSequence().map { it to curve(o.optJSONArray(it)) }
                        .filter { it.second.isNotEmpty() }
                        .sortedByDescending { it.second.last().second }
                        .map { ChartSeries(it.first, it.second) }.toList()
                } ?: emptyList()
                SectionCard {
                    BigFigure(
                        caption = "Patrimoine total au " + day(p.str("date")),
                        value = euros(total),
                        detail = "30 jours ${euros(v30, sign = true)} · 1 an ${euros(v1y, sign = true)}",
                        tone = v30,
                    )
                    if (byAccount.isNotEmpty()) {
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            FilterChip(selected = !perAccount, onClick = { perAccount = false }, label = { Text("Total") })
                            FilterChip(selected = perAccount, onClick = { perAccount = true }, label = { Text("Par compte") })
                        }
                    }
                    if (perAccount && byAccount.isNotEmpty()) {
                        InteractiveLineChart(byAccount, stacked = true)
                    } else {
                        InteractiveLineChart(listOf(ChartSeries("Total", totalCurve)))
                    }
                    Muted("Avant impôts. ${p.str("limites") ?: ""}")
                }
            }
            week(totalCurve)?.let { w ->
                item {
                    SectionCard("Cette semaine") {
                        InfoRow("Variation sur 7 jours", euros(w.change, sign = true), tone = w.change,
                            sub = "${pct(w.fraction)} depuis le ${day(w.since)}")
                        if (w.spark.size >= 2) Sparkline(w.spark, Modifier.fillMaxWidth().padding(top = 4.dp))
                        Muted("Patrimoine total avant impôts, tous comptes.")
                    }
                }
            }
            data.objOrNull("courbe_titres")?.let { t ->
                val value = curve(t.optJSONArray("valeur"))
                val cost = curve(t.optJSONArray("cout"))
                if (value.size >= 2) {
                    item {
                        SectionCard("Valeur et montant investi") {
                            InteractiveLineChart(
                                listOf(
                                    ChartSeries("Valeur des titres", value),
                                    ChartSeries("Montant investi (coût)", cost, dashed = true),
                                ),
                            )
                            Muted("Compte-titres et PEA. L'écart entre les deux courbes est la plus-value latente " +
                                "(avant impôts), hors PEG Airbus et espèces.")
                        }
                    }
                }
            }
            item {
                val accounts = p.objOrNull("comptes")?.numbers()?.filter { it.second > 0 }
                    ?.sortedByDescending { it.second }.orEmpty()
                val securities = data.strings("comptes_titres").toSet()
                SectionCard("Par compte") {
                    if (accounts.isNotEmpty()) {
                        DonutChart(
                            slices = accounts.map { (name, value) -> Slice(name, value, key = name) },
                            centerTitle = "Total",
                            centerValue = euros(total),
                            onSliceClick = { s -> if (s.label in securities) nav.navigate(Routes.PORTEFEUILLE) },
                        )
                    }
                    InfoRow("Plus-values latentes (titres)", euros(p.num("plus_values_latentes"), sign = true),
                        tone = p.num("plus_values_latentes"), sub = "Coût investi ${euros(p.num("cout_investi"))}")
                    InfoRow("Plus-values réalisées (cumul)", euros(p.num("plus_values_realisees_cumul"), sign = true),
                        tone = p.num("plus_values_realisees_cumul"))
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

private class Week(val change: Double, val fraction: Double?, val since: String, val spark: List<Double>)

/** 7-day move of the total curve, from the last point on or before (last date - 7 days); null if the curve is too short. */
private fun week(points: List<Pair<String, Double>>): Week? {
    val last = points.lastOrNull() ?: return null
    val end = runCatching { LocalDate.parse(last.first) }.getOrNull() ?: return null
    val ref = points.lastOrNull { p -> runCatching { !LocalDate.parse(p.first).isAfter(end.minusDays(7)) }.getOrDefault(false) }
        ?: return null
    val from = end.minusDays(7)
    val spark = points.filter { p -> runCatching { !LocalDate.parse(p.first).isBefore(from) }.getOrDefault(false) }
        .map { it.second }
    return Week(last.second - ref.second, if (ref.second != 0.0) last.second / ref.second - 1 else null, ref.first, spark)
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
