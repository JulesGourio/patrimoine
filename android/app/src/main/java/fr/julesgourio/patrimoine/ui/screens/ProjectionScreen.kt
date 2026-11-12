package fr.julesgourio.patrimoine.ui.screens

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import fr.julesgourio.patrimoine.engine.Engine
import fr.julesgourio.patrimoine.ui.components.CallScreen
import fr.julesgourio.patrimoine.ui.components.InfoRow
import fr.julesgourio.patrimoine.ui.components.Muted
import fr.julesgourio.patrimoine.ui.components.ScreenScaffold
import fr.julesgourio.patrimoine.ui.components.SectionCard
import fr.julesgourio.patrimoine.ui.components.euros
import fr.julesgourio.patrimoine.ui.components.list
import fr.julesgourio.patrimoine.ui.components.num
import fr.julesgourio.patrimoine.ui.components.number
import fr.julesgourio.patrimoine.ui.components.objOrNull
import fr.julesgourio.patrimoine.ui.components.pct
import fr.julesgourio.patrimoine.ui.components.rememberCall
import fr.julesgourio.patrimoine.ui.components.str
import org.json.JSONArray
import org.json.JSONObject
import kotlin.math.abs

/** Paramètre modifiable : clé du moteur (celle de `hypotheses` et de l'argument de `projection`) et libellé. */
private val CHAMPS = listOf(
    "horizon_ans" to "Horizon (ans, 1 à 40)",
    "epargne_mensuelle" to "Épargne mensuelle (€)",
    "hausse_epargne_pct" to "Hausse de l'épargne (% par an)",
    "objectif_eur" to "Objectif (€)",
    "part_actions_pct" to "Part en actions (%)",
    "rendement_actions_pct" to "Rendement des actions (% par an)",
    "volatilite_pct" to "Volatilité des actions (% par an)",
    "rendement_livrets_pct" to "Rendement des livrets (% par an)",
    "inflation_pct" to "Inflation (% par an)",
)

private fun valeur(s: String?): Double? = s?.trim()?.replace(',', '.')?.toDoubleOrNull()

/** « 2041-03 » devient « 03/2041 ». */
private fun mois(label: String?): String {
    if (label == null) return "—"
    val p = label.split("-")
    return if (p.size == 2) "${p[1]}/${p[0]}" else label
}

private fun JSONObject.suite(key: String): List<Double> {
    val a: JSONArray = optJSONArray(key) ?: return emptyList()
    return (0 until a.length()).map { i -> a.optDouble(i).takeUnless { it.isNaN() } ?: 0.0 }
}

/** Simulation Monte-Carlo de l'évolution du patrimoine (outil `projection`), avec des hypothèses modifiables. */
@Composable
fun ProjectionScreen(back: () -> Unit) {
    // Champs de saisie (texte) et valeurs appliquées au dernier calcul ; vide au départ = valeurs du moteur.
    val champs = remember { mutableStateMapOf<String, String>() }
    var appliquees by remember { mutableStateOf<Map<String, Double>>(emptyMap()) }
    val state = rememberCall(
        "projection",
        Engine.args(
            "horizon_ans" to appliquees["horizon_ans"]?.toInt(),
            "epargne_mensuelle" to appliquees["epargne_mensuelle"],
            "hausse_epargne_pct" to appliquees["hausse_epargne_pct"],
            "objectif_eur" to appliquees["objectif_eur"],
            "part_actions_pct" to appliquees["part_actions_pct"],
            "rendement_actions_pct" to appliquees["rendement_actions_pct"],
            "volatilite_pct" to appliquees["volatilite_pct"],
            "rendement_livrets_pct" to appliquees["rendement_livrets_pct"],
            "inflation_pct" to appliquees["inflation_pct"],
        ).also { j -> j.keys().asSequence().toList().filter { j.isNull(it) }.forEach { j.remove(it) } },
        appliquees,
    )
    ScreenScaffold("Projection", onBack = back) { padding ->
        CallScreen(state, padding) { data ->
            val erreur = data.str("erreur")
            val hyp = data.objOrNull("hypotheses")
            val final = data.objOrNull("final")
            val depart = data.objOrNull("depart")

            item {
                SectionCard("Hypothèses") {
                    // Première réponse : les champs reprennent les valeurs du moteur.
                    LaunchedEffect(hyp?.toString()) {
                        if (hyp != null && champs.isEmpty()) {
                            CHAMPS.forEach { (k, _) -> hyp.num(k)?.let { champs[k] = if (it == Math.rint(it)) it.toLong().toString() else it.toString() } }
                        }
                    }
                    if (erreur != null) {
                        Text(erreur, color = MaterialTheme.colorScheme.error)
                        if (erreur.contains("historique")) Muted("Lance une synchronisation pour disposer de l'historique.")
                    }
                    if (depart != null) {
                        Muted("Départ : ${euros(depart.num("total"))} (actions ${euros(depart.num("risque"))}, " +
                            "livrets et liquidités ${euros(depart.num("sur"))})")
                    }
                    CHAMPS.forEach { (k, label) ->
                        OutlinedTextField(
                            value = champs[k] ?: "",
                            onValueChange = { champs[k] = it },
                            label = { Text(label) },
                            singleLine = true,
                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                            modifier = Modifier.fillMaxWidth(),
                        )
                    }
                    Button(
                        onClick = {
                            appliquees = CHAMPS.mapNotNull { (k, _) -> valeur(champs[k])?.let { k to it } }.toMap()
                        },
                        modifier = Modifier.fillMaxWidth(),
                    ) { Text("Recalculer") }
                }
            }

            if (final != null) {
                val horizon = hyp?.num("horizon_ans")?.toInt()
                item {
                    SectionCard("Dans ${horizon ?: "—"} ans") {
                        InfoRow("Médiane (euros courants)", euros(final.num("mediane")))
                        InfoRow("Médiane en euros d'aujourd'hui", euros(final.num("mediane_reelle")),
                            sub = "Après inflation de ${number(hyp?.num("inflation_pct"), 1)} % par an")
                        InfoRow("Scénario prudent (1 chance sur 10 de faire moins)", euros(final.num("p10")),
                            sub = "${euros(final.num("p10_reel"))} d'aujourd'hui")
                        InfoRow("Scénario favorable (1 chance sur 10 de faire mieux)", euros(final.num("p90")),
                            sub = "${euros(final.num("p90_reel"))} d'aujourd'hui")
                    }
                }
                item {
                    SectionCard("Versé et gains (médiane)") {
                        InfoRow("Versé de ta poche", euros(data.num("verse")), sub = "Patrimoine actuel plus toutes les épargnes futures")
                        InfoRow("Gains attendus", euros(data.num("gains_medians"), sign = true),
                            tone = data.num("gains_medians"))
                    }
                }
                val objectif = data.objOrNull("objectif")
                if (objectif != null) {
                    item {
                        SectionCard("Objectif de ${euros(objectif.num("montant"))}") {
                            InfoRow("Chance de l'atteindre", pct(objectif.num("chance"), sign = false, digits = 0))
                            InfoRow("Mois où la médiane atteint l'objectif",
                                objectif.str("mois_median")?.let { mois(it) } ?: "pas dans l'horizon (médiane)")
                        }
                    }
                }
                val serie = data.objOrNull("serie")
                if (serie != null) {
                    item {
                        SectionCard("Trajectoires") {
                            TrajectoiresChart(serie)
                        }
                    }
                }
            }

            val leviers = data.list("leviers").sortedByDescending { abs(it.num("effet") ?: 0.0) }
            if (leviers.isNotEmpty()) {
                item {
                    SectionCard("Ce qui change le plus le résultat") {
                        Muted("Effet sur la médiane à l'horizon")
                        leviers.forEach { l ->
                            InfoRow(l.str("levier") ?: "—", euros(l.num("effet"), sign = true), tone = l.num("effet"))
                        }
                    }
                }
            }

            item {
                Muted(
                    "Les rendements passés ne préjugent pas des rendements futurs. Il s'agit d'une simulation " +
                        "(2000 scénarios aléatoires, avant impôts), pas d'une promesse.",
                )
            }
        }
    }
}

@Composable
private fun LegendeItem(color: Color, text: String) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Canvas(Modifier.size(10.dp)) { drawCircle(color) }
        Spacer(Modifier.width(4.dp))
        Text(text, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

/** Zones p10–p90 et p25–p75, médiane, médiane en euros d'aujourd'hui et versé cumulé. */
@Composable
private fun TrajectoiresChart(serie: JSONObject) {
    val p10 = serie.suite("p10")
    val p25 = serie.suite("p25")
    val p50 = serie.suite("p50")
    val p75 = serie.suite("p75")
    val p90 = serie.suite("p90")
    val reelle = serie.suite("mediane_reelle")
    val verse = serie.suite("verse")
    val dates = serie.optJSONArray("dates")
    val n = p50.size
    if (n < 2 || p10.size != n || p90.size != n) {
        Muted("Pas assez de points pour une courbe.")
        return
    }
    val principal = MaterialTheme.colorScheme.primary
    val reel = MaterialTheme.colorScheme.tertiary
    val neutre = MaterialTheme.colorScheme.onSurfaceVariant
    val max = p90.max().takeIf { it > 0 } ?: 1.0
    Canvas(Modifier.fillMaxWidth().height(220.dp)) {
        val step = size.width / (n - 1)
        fun x(i: Int) = i * step
        fun y(v: Double) = (size.height * (1 - v / max)).toFloat()
        fun bande(bas: List<Double>, haut: List<Double>, couleur: Color) {
            if (bas.size != n || haut.size != n) return
            val path = Path().apply {
                moveTo(x(0), y(haut[0]))
                for (i in 1 until n) lineTo(x(i), y(haut[i]))
                for (i in n - 1 downTo 0) lineTo(x(i), y(bas[i]))
                close()
            }
            drawPath(path, couleur)
        }
        fun ligne(v: List<Double>, couleur: Color, epaisseur: Float, tirets: Boolean = false) {
            if (v.size != n) return
            val path = Path().apply {
                moveTo(x(0), y(v[0]))
                for (i in 1 until n) lineTo(x(i), y(v[i]))
            }
            drawPath(
                path, couleur,
                style = Stroke(
                    width = epaisseur.dp.toPx(), cap = StrokeCap.Round,
                    pathEffect = if (tirets) PathEffect.dashPathEffect(floatArrayOf(14f, 10f)) else null,
                ),
            )
        }
        bande(p10, p90, principal.copy(alpha = 0.12f))
        bande(p25, p75, principal.copy(alpha = 0.25f))
        ligne(verse, neutre, 1.5f, tirets = true)
        ligne(reelle, reel, 2f)
        ligne(p50, principal, 2.5f)
        drawLine(neutre.copy(alpha = 0.4f), Offset(0f, size.height), Offset(size.width, size.height), 1.dp.toPx())
    }
    Row(Modifier.fillMaxWidth()) {
        Muted(mois(dates?.optString(0)))
        Spacer(Modifier.weight(1f))
        Muted("max ${euros(max)}")
        Spacer(Modifier.weight(1f))
        Muted(mois(dates?.optString(n - 1)))
    }
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        LegendeItem(principal, "Médiane")
        LegendeItem(reel, "Médiane réelle")
        LegendeItem(neutre, "Versé")
    }
    Muted("Zones : 8 scénarios sur 10 (clair) et 1 sur 2 (foncé).")
}
