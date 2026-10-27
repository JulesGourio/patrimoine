package fr.julesgourio.patrimoine.ui.screens

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.navigation.NavController
import fr.julesgourio.patrimoine.ui.Routes
import fr.julesgourio.patrimoine.ui.components.CallScreen
import fr.julesgourio.patrimoine.ui.components.DonutChart
import fr.julesgourio.patrimoine.ui.components.HorizontalBars
import fr.julesgourio.patrimoine.ui.components.InfoRow
import fr.julesgourio.patrimoine.ui.components.Loaded
import fr.julesgourio.patrimoine.ui.components.Muted
import fr.julesgourio.patrimoine.ui.components.ScreenScaffold
import fr.julesgourio.patrimoine.ui.components.SectionCard
import fr.julesgourio.patrimoine.ui.components.Slice
import fr.julesgourio.patrimoine.ui.components.Sparkline
import fr.julesgourio.patrimoine.ui.components.day
import fr.julesgourio.patrimoine.ui.components.euros
import fr.julesgourio.patrimoine.ui.components.gainColor
import fr.julesgourio.patrimoine.ui.components.list
import fr.julesgourio.patrimoine.ui.components.num
import fr.julesgourio.patrimoine.ui.components.objOrNull
import fr.julesgourio.patrimoine.ui.components.pct
import fr.julesgourio.patrimoine.ui.components.rememberCall
import fr.julesgourio.patrimoine.ui.components.str
import org.json.JSONArray
import org.json.JSONObject

/** Part d'une seule ligne au-delà de laquelle on signale la concentration. */
private const val SEUIL_CONCENTRATION = 0.25

private val HORIZONS = listOf(
    "perf_1m" to "1 mois",
    "perf_3m" to "3 mois",
    "perf_ytd" to "Depuis le 1er janv.",
    "perf_1an" to "1 an",
)

/** Mini-série de cours (3 mois) d'une ligne, fournie par l'écran `portefeuille`. */
private fun JSONObject.serie(isin: String?): List<Double> {
    if (isin == null) return emptyList()
    val a: JSONArray = objOrNull("series")?.optJSONArray(isin) ?: return emptyList()
    return (0 until a.length()).mapNotNull { i -> a.optDouble(i).takeUnless { it.isNaN() } }
}

/** Airbus (PEG + direct) est regroupé en une seule ligne pour la concentration. */
private fun JSONObject.groupe(): String {
    val nom = str("name") ?: str("isin") ?: "—"
    return if (nom.contains("Airbus", ignoreCase = true)) "Airbus (PEG + direct)" else nom
}

@Composable
fun PortefeuilleScreen(nav: NavController) {
    var horizon by remember { mutableStateOf(HORIZONS[0].first) }
    ScreenScaffold("Portefeuille") { padding ->
        CallScreen(rememberCall("portefeuille"), padding) { data ->
            val lignes = data.list("positions")
            val valeurTotale = lignes.sumOf { it.num("value") ?: 0.0 }
            val avecGain = lignes.filter { it.num("gain") != null }
            val gainTotal = avecGain.sumOf { it.num("gain") ?: 0.0 }
            val coutTotal = avecGain.sumOf { it.num("cost") ?: 0.0 }
            val partGain = if (avecGain.isNotEmpty() && coutTotal > 0) gainTotal / coutTotal else null
            val patrimoine = data.num("patrimoine_total")

            item {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    Tuile(
                        "Valeur", euros(valeurTotale),
                        sub = "${lignes.size} lignes · compte-titres, PEA et PEG",
                    )
                    Tuile(
                        "Gain latent", if (avecGain.isEmpty()) "—" else euros(gainTotal, sign = true),
                        sub = if (partGain == null) null else pct(partGain) + " sur " + euros(coutTotal) + " investis",
                        tone = if (avecGain.isEmpty()) null else gainTotal,
                    )
                }
            }
            if (lignes.isEmpty()) {
                item { Muted("Aucune ligne en portefeuille.") }
            } else {
                item {
                    SectionCard("Lignes — toucher pour ouvrir la fiche") {
                        for (l in lignes) LigneRow(l, data.serie(l.str("isin")), nav)
                        Muted("Mini-courbe = cours sur 3 mois.")
                    }
                }
                val gains = avecGain.sortedByDescending { it.num("gain") }
                if (gains.isNotEmpty()) {
                    item {
                        SectionCard("Gains et pertes latents") {
                            HorizontalBars(
                                gains.map { Slice(it.str("name") ?: it.str("isin") ?: "—", it.num("gain") ?: 0.0) },
                                valueFormat = { euros(it, sign = true) },
                                colorByTone = true,
                            )
                        }
                    }
                }
                item { Concentration(lignes, valeurTotale, patrimoine) }
                item {
                    SectionCard("Performance par horizon (cours)") {
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            for ((cle, libelle) in HORIZONS) {
                                FilterChip(
                                    selected = horizon == cle,
                                    onClick = { horizon = cle },
                                    label = { Text(libelle, maxLines = 1, overflow = TextOverflow.Ellipsis) },
                                )
                            }
                        }
                        val perfs = lignes.filter { it.num(horizon) != null }.sortedByDescending { it.num(horizon) }
                        if (perfs.isEmpty()) {
                            Muted("Pas de cours sur cet horizon.")
                        } else {
                            HorizontalBars(
                                perfs.map { Slice(it.str("name") ?: it.str("isin") ?: "—", it.num(horizon) ?: 0.0) },
                                valueFormat = { pct(it) },
                                colorByTone = true,
                            )
                        }
                    }
                }
            }
            item { VentesRealisees() }
        }
    }
}

/** Un indicateur en carte, à placer dans une [Row] (deux par ligne). */
@Composable
internal fun RowScope.Tuile(label: String, value: String, sub: String? = null, tone: Double? = null) {
    Card(
        Modifier.weight(1f),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLow),
    ) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Muted(label)
            Text(
                value,
                style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.SemiBold,
                color = if (tone != null) gainColor(tone) else MaterialTheme.colorScheme.onSurface,
            )
            if (sub != null) Muted(sub)
        }
    }
}

@Composable
private fun LigneRow(l: JSONObject, serie: List<Double>, nav: NavController) {
    val gain = l.num("gain")
    val cible = l.str("isin") ?: l.str("symbole_yahoo")
    Row(
        Modifier
            .fillMaxWidth()
            .let { if (cible != null) it.clickable { nav.navigate(Routes.titre(cible)) } else it }
            .padding(vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Text(
                l.str("name") ?: l.str("isin") ?: "—",
                style = MaterialTheme.typography.bodyLarge,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
            )
            Muted((l.str("account") ?: "—") + " · " + pct(l.num("weight"), sign = false, digits = 0) + " du portefeuille")
        }
        if (serie.size >= 2) Sparkline(serie, Modifier.width(56.dp).padding(horizontal = 6.dp))
        Column(horizontalAlignment = Alignment.End) {
            Text(euros(l.num("value")), style = MaterialTheme.typography.bodyLarge, fontWeight = FontWeight.Medium)
            Text(
                if (gain == null) "—" else euros(gain, sign = true) + " (" + pct(l.num("gain_pct")) + ")",
                style = MaterialTheme.typography.bodySmall,
                color = gainColor(gain),
            )
        }
    }
}

@Composable
private fun Concentration(lignes: List<JSONObject>, total: Double, patrimoine: Double?) {
    val parts = lignes.groupBy { it.groupe() }
        .map { (nom, ls) -> Slice(nom, ls.sumOf { it.num("value") ?: 0.0 }) }
        .filter { it.value > 0 }
        .sortedByDescending { it.value }
    SectionCard("Concentration") {
        if (parts.isEmpty() || total <= 0) {
            Muted("Rien à afficher.")
        } else {
            DonutChart(parts, centerTitle = "Titres", centerValue = euros(total))
            val top = parts[0]
            val partTitres = top.value / total
            val partPatrimoine = if (patrimoine != null && patrimoine > 0) top.value / patrimoine else null
            if (partTitres > SEUIL_CONCENTRATION) {
                Text(
                    "Concentration : ${top.label} = ${pct(partTitres, sign = false, digits = 0)} des titres" +
                        (partPatrimoine?.let { " et ${pct(it, sign = false, digits = 0)} du patrimoine total" } ?: "") + ".",
                    style = MaterialTheme.typography.bodyMedium,
                    color = gainColor(-1.0),
                )
            } else {
                Muted(
                    "Aucune ligne ne dépasse ${pct(SEUIL_CONCENTRATION, sign = false, digits = 0)} des titres " +
                        "(la plus grosse : ${top.label}, ${pct(partTitres, sign = false, digits = 0)}).",
                )
            }
        }
    }
}

@Composable
private fun VentesRealisees() {
    var ouvert by remember { mutableStateOf(false) }
    SectionCard(title = "Ventes réalisées", onClick = { ouvert = !ouvert }) {
        if (!ouvert) {
            Muted("Toucher pour afficher")
        } else {
            Loaded(rememberCall("ventes_realisees")) { data ->
                val ventes = data.list("ventes")
                if (ventes.isEmpty()) Muted("Aucune vente enregistrée.")
                Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    for (v in ventes) {
                        val gain = v.num("gain")
                        InfoRow(
                            v.str("name") ?: v.str("isin") ?: "—",
                            if (gain == null) "—" else euros(gain, sign = true),
                            tone = gain,
                            sub = day(v.str("date")),
                        )
                    }
                }
            }
        }
    }
}
