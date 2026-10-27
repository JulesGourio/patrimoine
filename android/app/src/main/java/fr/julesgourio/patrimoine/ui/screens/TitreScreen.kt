package fr.julesgourio.patrimoine.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import fr.julesgourio.patrimoine.engine.Engine
import fr.julesgourio.patrimoine.ui.components.CallScreen
import fr.julesgourio.patrimoine.ui.components.ChartSeries
import fr.julesgourio.patrimoine.ui.components.InfoRow
import fr.julesgourio.patrimoine.ui.components.InteractiveLineChart
import fr.julesgourio.patrimoine.ui.components.Load
import fr.julesgourio.patrimoine.ui.components.Muted
import fr.julesgourio.patrimoine.ui.components.RangeBar
import fr.julesgourio.patrimoine.ui.components.RangeMarker
import fr.julesgourio.patrimoine.ui.components.ScreenScaffold
import fr.julesgourio.patrimoine.ui.components.SectionCard
import fr.julesgourio.patrimoine.ui.components.day
import fr.julesgourio.patrimoine.ui.components.euros
import fr.julesgourio.patrimoine.ui.components.gainColor
import fr.julesgourio.patrimoine.ui.components.list
import fr.julesgourio.patrimoine.ui.components.num
import fr.julesgourio.patrimoine.ui.components.number
import fr.julesgourio.patrimoine.ui.components.pct
import fr.julesgourio.patrimoine.ui.components.rememberCall
import fr.julesgourio.patrimoine.ui.components.str
import fr.julesgourio.patrimoine.ui.components.usd
import org.json.JSONObject
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId

private val COULEUR_PMP = Color(0xFFFFB020)
private val COULEUR_OBJECTIF = Color(0xFF2ECC8F)

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

/** Points [date, prix] de l'outil `cours`. */
private fun JSONObject.points(): List<Pair<String, Double>> {
    val a = optJSONArray("cours") ?: return emptyList()
    return (0 until a.length()).mapNotNull { i ->
        val p = a.optJSONArray(i) ?: return@mapNotNull null
        val v = p.optDouble(1)
        if (v.isNaN()) null else p.optString(0) to v
    }
}

/** Moyenne mobile simple sur [n] points (la série commence au n-ième point). */
private fun moyenneMobile(pts: List<Pair<String, Double>>, n: Int): List<Pair<String, Double>> {
    if (pts.size < n) return emptyList()
    val out = ArrayList<Pair<String, Double>>(pts.size - n + 1)
    var somme = 0.0
    for (i in pts.indices) {
        somme += pts[i].second
        if (i >= n) somme -= pts[i - n].second
        if (i >= n - 1) out.add(pts[i].first to somme / n)
    }
    return out
}

@Composable
fun TitreScreen(symbole: String, onBack: () -> Unit) {
    val marche = rememberCall("marche", Engine.args("titre" to symbole, "periode" to "1y"), symbole)
    val coursState = rememberCall("cours", Engine.args("isin" to symbole), symbole)
    val posState = rememberCall("positions")
    val cours = (coursState.load as? Load.Done)?.data
    val isin = cours?.str("isin")
    val lignes = (posState.load as? Load.Done)?.data?.list("positions").orEmpty().filter {
        it.str("isin") == symbole || it.str("symbole_yahoo") == symbole || (isin != null && it.str("isin") == isin)
    }
    ScreenScaffold(lignes.firstOrNull()?.str("name") ?: symbole, onBack = onBack) { padding ->
        CallScreen(marche, padding) { d ->
            val devise = d.str("currency")
            val enEuros = devise == null || devise == "EUR"
            val prix: (Double?) -> String = { x ->
                if (x == null) "—" else if (enEuros) euros(x, cents = true) else number(x) + " " + devise
            }
            val pts = cours?.points().orEmpty()
            val pmp = cours?.num("pmp")
            val detenue = lignes.isNotEmpty()
            val valeur = lignes.sumOf { it.num("value") ?: 0.0 }
            val quantite = lignes.sumOf { it.num("quantity") ?: 0.0 }
            val avecGain = lignes.filter { it.num("gain") != null }
            val gain = avecGain.sumOf { it.num("gain") ?: 0.0 }
            val cout = avecGain.sumOf { it.num("cost") ?: 0.0 }
            val gainPct = if (cout > 0) gain / cout else null
            val coursActuel = lignes.firstOrNull()?.num("price") ?: pts.lastOrNull()?.second ?: d.num("dernier_cours")
            val veille = if (pts.size >= 2) pts[pts.size - 1].second / pts[pts.size - 2].second - 1 else null

            item {
                SectionCard {
                    Muted(listOfNotNull(d.str("symbole"), d.str("sector")).joinToString(" · "))
                    Text(
                        if (lignes.isNotEmpty() || pts.isNotEmpty()) euros(coursActuel, cents = true) else prix(coursActuel),
                        style = MaterialTheme.typography.displaySmall,
                        fontWeight = FontWeight.SemiBold,
                    )
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        Text(
                            pct(lignes.firstOrNull()?.num("perf_1j") ?: veille),
                            style = MaterialTheme.typography.bodyMedium,
                            color = gainColor(lignes.firstOrNull()?.num("perf_1j") ?: veille),
                        )
                        val dernier = pts.lastOrNull()?.first?.take(10)
                        val quand = if (dernier == null || dernier == LocalDate.now().toString()) "aujourd'hui"
                        else "au " + day(dernier).take(5)
                        Muted(quand + (pmp?.let { " · PMP " + euros(it, cents = true) } ?: ""))
                    }
                    val series = remember(cours) {
                        if (pts.size < 2) {
                            emptyList()
                        } else {
                            listOfNotNull(
                                ChartSeries("Cours", pts),
                                pmp?.let { p -> ChartSeries("PMP", pts.map { it.first to p }, dashed = true) },
                                moyenneMobile(pts, 50).takeIf { it.size >= 2 }?.let { ChartSeries("MM 50 j", it) },
                                moyenneMobile(pts, 200).takeIf { it.size >= 2 }?.let { ChartSeries("MM 200 j", it) },
                            )
                        }
                    }
                    if (series.isNotEmpty()) {
                        InteractiveLineChart(series, valueFormat = { euros(it, cents = true) })
                        Muted("Pointillé = ton prix de revient. Moyennes mobiles 50 j / 200 j.")
                    } else {
                        Muted("Pas de série de cours enregistrée pour ce titre.")
                    }
                }
            }
            item {
                Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        Tuile(
                            "Ta ligne", if (detenue) euros(valeur) else "—",
                            sub = if (detenue) number(quantite, 2) + " titres" else "non détenue",
                        )
                        Tuile(
                            "+/- latente", if (avecGain.isEmpty()) "—" else euros(gain, sign = true),
                            sub = gainPct?.let { pct(it) },
                            tone = if (avecGain.isEmpty()) null else gain,
                        )
                    }
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        Tuile("Volatilité", pct(d.num("volatilite_annuelle"), sign = false, digits = 0), sub = "annualisée")
                        Tuile(
                            "Plus forte baisse", pct(d.num("plus_forte_baisse"), digits = 0), sub = "sur 1 an",
                            tone = d.num("plus_forte_baisse"),
                        )
                    }
                }
            }

            val bas = d.num("fiftyTwoWeekLow")
            val haut = d.num("fiftyTwoWeekHigh")
            val objectif = d.num("targetMeanPrice")
            if (bas != null && haut != null) {
                item {
                    val couleurCours = MaterialTheme.colorScheme.primary
                    val marqueurs = listOfNotNull(
                        d.num("dernier_cours")?.let { RangeMarker("Cours", it, couleurCours) },
                        // The PMP is in euros: it only fits the scale of a listing quoted in euros.
                        if (enEuros) pmp?.let { RangeMarker("PMP", it, COULEUR_PMP) } else null,
                        objectif?.let { RangeMarker("Objectif", it, COULEUR_OBJECTIF) },
                    )
                    SectionCard("Fourchette 52 semaines et objectif des analystes") {
                        Muted("52 sem. " + prix(bas) + " → " + prix(haut))
                        RangeBar(bas, haut, marqueurs, valueFormat = { prix(it) })
                        val reco = d.str("recommendationKey")
                        if (objectif != null || reco != null) {
                            Muted(
                                listOfNotNull(
                                    objectif?.let {
                                        "Objectif moyen " + prix(it) +
                                            (if (d.num("targetLowPrice") != null && d.num("targetHighPrice") != null) {
                                                " (" + prix(d.num("targetLowPrice")) + "–" + prix(d.num("targetHighPrice")) + ")"
                                            } else ""
                                            )
                                    },
                                    d.num("numberOfAnalystOpinions")?.let { number(it, 0) + " avis" },
                                    reco?.let { "« $it »" },
                                ).joinToString(" · "),
                            )
                        }
                    }
                }
            }

            val cap = d.num("marketCap")
            item {
                SectionCard("Fondamentaux") {
                    InfoRow("PER (réel / prévu)", number(d.num("trailingPE"), 1) + " / " + number(d.num("forwardPE"), 1))
                    InfoRow(
                        "Rendement du dividende",
                        // Yahoo gives this one in percent already (0.41 = 0.41 %).
                        d.num("dividendYield")?.let { number(it) + " %" } ?: "—",
                    )
                    InfoRow("Croissance du CA", pct(d.num("revenueGrowth")), tone = d.num("revenueGrowth"))
                    InfoRow("Marge nette", pct(d.num("profitMargins"), sign = false))
                    InfoRow("Bêta", number(d.num("beta")))
                    InfoRow(
                        "Capitalisation",
                        when {
                            cap == null -> "—"
                            devise == "USD" -> usd(cap)
                            enEuros -> number(cap / 1e9, 0) + " Md€"
                            else -> number(cap / 1e9, 0) + " Md " + devise
                        },
                    )
                }
            }

            val operations = cours?.list("operations").orEmpty().sortedByDescending { it.str("date") }.take(15)
            if (operations.isNotEmpty()) {
                item {
                    SectionCard("Opérations de la ligne") {
                        for (o in operations) {
                            val vente = o.str("sens") == "vente"
                            InfoRow(
                                (if (vente) "Vente" else "Achat") + " · " + number(o.num("quantite"), 4) + " titres",
                                euros(o.num("prix"), cents = true),
                                sub = day(o.str("date")),
                            )
                        }
                    }
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
