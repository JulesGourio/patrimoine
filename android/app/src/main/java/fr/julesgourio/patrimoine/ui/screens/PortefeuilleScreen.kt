package fr.julesgourio.patrimoine.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.FilterChip
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
import fr.julesgourio.patrimoine.engine.Engine
import fr.julesgourio.patrimoine.ui.Routes
import fr.julesgourio.patrimoine.ui.components.BigFigure
import fr.julesgourio.patrimoine.ui.components.CallScreen
import fr.julesgourio.patrimoine.ui.components.InfoRow
import fr.julesgourio.patrimoine.ui.components.Loaded
import fr.julesgourio.patrimoine.ui.components.Muted
import fr.julesgourio.patrimoine.ui.components.ScreenScaffold
import fr.julesgourio.patrimoine.ui.components.SectionCard
import fr.julesgourio.patrimoine.ui.components.day
import fr.julesgourio.patrimoine.ui.components.euros
import fr.julesgourio.patrimoine.ui.components.list
import fr.julesgourio.patrimoine.ui.components.num
import fr.julesgourio.patrimoine.ui.components.number
import fr.julesgourio.patrimoine.ui.components.objOrNull
import fr.julesgourio.patrimoine.ui.components.pct
import fr.julesgourio.patrimoine.ui.components.rememberCall
import fr.julesgourio.patrimoine.ui.components.str
import fr.julesgourio.patrimoine.ui.components.usd
import org.json.JSONObject
import java.time.Instant
import java.time.ZoneId

private enum class Tri(val label: String) {
    VALEUR("Valeur"),
    PLUS_VALUE("Plus-value %"),
    PERF_1J("Perf. 1 j"),
}

private fun JSONObject.triValue(tri: Tri): Double = when (tri) {
    Tri.VALEUR -> num("value")
    Tri.PLUS_VALUE -> num("gain_pct")
    Tri.PERF_1J -> num("perf_1j")
} ?: Double.NEGATIVE_INFINITY

@Composable
fun PortefeuilleScreen(nav: NavController) {
    var tri by remember { mutableStateOf(Tri.VALEUR) }
    ScreenScaffold("Portefeuille") { padding ->
        CallScreen(rememberCall("positions"), padding) { data ->
            val lignes = data.list("positions")
            val valeurTotale = lignes.sumOf { it.num("value") ?: 0.0 }
            val avecGain = lignes.filter { it.num("gain") != null }
            val gainTotal = avecGain.sumOf { it.num("gain") ?: 0.0 }
            val coutTotal = avecGain.sumOf { it.num("cost") ?: 0.0 }
            val partGain = if (avecGain.isNotEmpty() && coutTotal > 0) gainTotal / coutTotal else null

            item {
                SectionCard {
                    BigFigure("Valeur des lignes", euros(valeurTotale))
                    InfoRow(
                        "Plus-value latente",
                        if (avecGain.isEmpty()) "—" else euros(gainTotal, sign = true),
                        tone = if (avecGain.isEmpty()) null else gainTotal,
                        sub = "hors PEG, sans coût d'achat connu",
                    )
                    InfoRow(
                        "Part du coût investi",
                        pct(partGain),
                        tone = partGain,
                    )
                }
            }
            item {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    for (t in Tri.values()) {
                        FilterChip(
                            selected = tri == t,
                            onClick = { tri = t },
                            label = { Text(t.label) },
                        )
                    }
                }
            }
            if (lignes.isEmpty()) {
                item { Muted("Aucune ligne en portefeuille.") }
            }
            items(lignes.sortedByDescending { it.triValue(tri) }) { ligne ->
                LigneCard(ligne, nav)
            }
            item { VentesRealisees() }
        }
    }
}

@Composable
private fun LigneCard(l: JSONObject, nav: NavController) {
    val gain = l.num("gain")
    val gainPct = l.num("gain_pct")
    val cible = l.str("symbole_yahoo") ?: l.str("isin")
    SectionCard(
        onClick = cible?.let { c -> { nav.navigate(Routes.titre(c)) } },
    ) {
        Text(
            l.str("name") ?: l.str("isin") ?: "—",
            style = MaterialTheme.typography.titleMedium,
            fontWeight = FontWeight.SemiBold,
        )
        Muted(l.str("account") ?: "—")
        InfoRow("Valeur", euros(l.num("value")), sub = "poids " + pct(l.num("weight"), sign = false))
        InfoRow(
            "Plus-value",
            if (gain == null) "—" else euros(gain, sign = true),
            tone = gain,
            sub = if (gainPct == null) null else pct(gainPct),
        )
        Muted(
            "Perf. 1 j " + pct(l.num("perf_1j")) +
                " · 1 m " + pct(l.num("perf_1m")) +
                " · 1 an " + pct(l.num("perf_1an")),
        )
        Muted(
            "PMP " + euros(l.num("unit_cost")) + " · cours " + euros(l.num("price")) +
                " · qté " + number(l.num("quantity"), 4),
        )
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

/** Date d'une actualité : texte ISO ou horodatage Unix (secondes). */
private fun dateActu(n: JSONObject): String {
    val brut = n.str("date") ?: return "—"
    val secondes = brut.toDoubleOrNull()
    return if (secondes != null && secondes > 1e9) {
        Instant.ofEpochSecond(secondes.toLong()).atZone(ZoneId.systemDefault()).toLocalDate().toString().let { day(it) }
    } else {
        day(brut)
    }
}

@Composable
fun TitreScreen(symbole: String, onBack: () -> Unit) {
    val state = rememberCall("marche", Engine.args("titre" to symbole, "periode" to "1y"), symbole)
    ScreenScaffold(symbole, onBack = onBack) { padding ->
        CallScreen(state, padding) { d ->
            val devise = d.str("currency")
            val cours = d.num("dernier_cours")
            val perfs = d.objOrNull("performances")
            val suffixeDevise = devise?.let { " $it" } ?: ""

            item {
                SectionCard {
                    Text(
                        d.str("longName") ?: d.str("symbole") ?: symbole,
                        style = MaterialTheme.typography.titleLarge,
                        fontWeight = FontWeight.SemiBold,
                    )
                    InfoRow(
                        "Dernier cours",
                        if (cours == null) "—" else number(cours) + suffixeDevise,
                        sub = "au " + day(d.str("date")),
                    )
                }
            }
            item {
                SectionCard("Performances") {
                    for ((cle, libelle) in listOf("1m" to "1 mois", "3m" to "3 mois", "6m" to "6 mois", "1an" to "1 an")) {
                        val p = perfs?.num(cle)
                        InfoRow(libelle, pct(p), tone = p)
                    }
                }
            }
            item {
                SectionCard("Risque et tendance") {
                    InfoRow("Volatilité annuelle", pct(d.num("volatilite_annuelle"), sign = false))
                    InfoRow("Plus forte baisse (1 an)", pct(d.num("plus_forte_baisse"), sign = false))
                    InfoRow("Moyenne mobile 50 j", d.num("moyenne_mobile_50")?.let { number(it) + suffixeDevise } ?: "—")
                    InfoRow("Moyenne mobile 200 j", d.num("moyenne_mobile_200")?.let { number(it) + suffixeDevise } ?: "—")
                    InfoRow("Plus haut 52 semaines", d.num("fiftyTwoWeekHigh")?.let { number(it) + suffixeDevise } ?: "—")
                    InfoRow("Plus bas 52 semaines", d.num("fiftyTwoWeekLow")?.let { number(it) + suffixeDevise } ?: "—")
                }
            }

            val cap = d.num("marketCap")
            val rendement = d.num("dividendYield")
            item {
                SectionCard("Valorisation") {
                    InfoRow("PER", number(d.num("trailingPE")))
                    InfoRow("PER anticipé", number(d.num("forwardPE")))
                    InfoRow(
                        "Capitalisation",
                        when {
                            cap == null -> "—"
                            devise == "USD" -> usd(cap)
                            else -> number(cap, 0) + suffixeDevise
                        },
                    )
                    InfoRow(
                        "Rendement du dividende",
                        when {
                            rendement == null -> "—"
                            rendement > 1 -> number(rendement) + " %"
                            else -> pct(rendement, sign = false)
                        },
                    )
                }
            }
            val profil = listOfNotNull(d.str("sector"), d.str("industry"), d.str("country"))
            if (profil.isNotEmpty()) {
                item {
                    SectionCard("Profil") {
                        d.str("sector")?.let { InfoRow("Secteur", it) }
                        d.str("industry")?.let { InfoRow("Industrie", it) }
                        d.str("country")?.let { InfoRow("Pays", it) }
                    }
                }
            }

            val reco = d.str("recommendationKey")
            val cible = d.num("targetMeanPrice")
            if (reco != null || cible != null) {
                item {
                    val ecart = if (cible != null && cours != null && cours != 0.0) cible / cours - 1 else null
                    SectionCard("Avis des analystes") {
                        InfoRow("Recommandation", reco ?: "—")
                        d.num("numberOfAnalystOpinions")?.let { InfoRow("Nombre d'avis", number(it, 0)) }
                        InfoRow("Objectif bas", d.num("targetLowPrice")?.let { number(it) + suffixeDevise } ?: "—")
                        InfoRow("Objectif moyen", cibleTexte(cible, suffixeDevise))
                        InfoRow("Objectif haut", d.num("targetHighPrice")?.let { number(it) + suffixeDevise } ?: "—")
                        InfoRow("Écart du moyen au cours", pct(ecart), tone = ecart)
                    }
                }
            }

            d.str("activite")?.let { texte ->
                item {
                    SectionCard("Activité") {
                        Text(texte, style = MaterialTheme.typography.bodyMedium)
                    }
                }
            }

            val actus = d.list("actualites")
            if (actus.isNotEmpty()) {
                item {
                    SectionCard("Actualités") {
                        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                            for (n in actus) {
                                Column {
                                    Text(n.str("titre") ?: "—", style = MaterialTheme.typography.bodyMedium)
                                    Muted((n.str("source") ?: "source inconnue") + " · " + dateActu(n))
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

private fun cibleTexte(x: Double?, suffixe: String): String = if (x == null) "—" else number(x) + suffixe
