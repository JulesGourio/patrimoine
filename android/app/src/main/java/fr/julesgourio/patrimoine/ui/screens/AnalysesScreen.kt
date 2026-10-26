package fr.julesgourio.patrimoine.ui.screens

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.AssistChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.unit.dp
import androidx.navigation.NavController
import fr.julesgourio.patrimoine.engine.Engine
import fr.julesgourio.patrimoine.ui.Routes
import fr.julesgourio.patrimoine.ui.components.CallScreen
import fr.julesgourio.patrimoine.ui.components.InfoRow
import fr.julesgourio.patrimoine.ui.components.Muted
import fr.julesgourio.patrimoine.ui.components.ScreenScaffold
import fr.julesgourio.patrimoine.ui.components.SectionCard
import fr.julesgourio.patrimoine.ui.components.day
import fr.julesgourio.patrimoine.ui.components.euros
import fr.julesgourio.patrimoine.ui.components.gainColor
import fr.julesgourio.patrimoine.ui.components.int
import fr.julesgourio.patrimoine.ui.components.list
import fr.julesgourio.patrimoine.ui.components.num
import fr.julesgourio.patrimoine.ui.components.objOrNull
import fr.julesgourio.patrimoine.ui.components.pct
import fr.julesgourio.patrimoine.ui.components.rememberCall
import fr.julesgourio.patrimoine.ui.components.str
import fr.julesgourio.patrimoine.ui.components.strings
import org.json.JSONObject

private fun kindLabel(kind: String?) = if (kind == "hebdo") "Semaine" else "Séance"

/** The analyses the Claude routines write (daily, weekly), newest first, and how their verdicts aged. */
@Composable
fun AnalysesScreen(nav: NavController) {
    val state = rememberCall("analyses", Engine.args("n" to 20))
    ScreenScaffold("Analyses") { padding ->
        CallScreen(state, padding) { data ->
            val list = data.list("analyses")
            if (list.isEmpty()) {
                item {
                    SectionCard {
                        Text("Aucune analyse pour l'instant.")
                        Muted("Les routines Claude écrivent l'analyse du jour (mardi–samedi, 8 h 05) et le bilan du " +
                            "dimanche ; l'appli les récupère toutes les heures (secret github_token dans les Réglages).")
                    }
                }
            }
            items(list) { a ->
                SectionCard(onClick = { a.int("id")?.let { nav.navigate(Routes.analyse(it)) } }) {
                    Muted("${kindLabel(a.str("type"))} du ${day(a.str("seance"))}")
                    Text(a.str("titre") ?: "Analyse", style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.SemiBold)
                    a.strings("points_cles").forEach { Text("• $it", style = MaterialTheme.typography.bodyMedium) }
                    val advice = a.list("conseils").filter { it.str("action") != "attendre" }
                    if (advice.isNotEmpty()) {
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            advice.take(3).forEach { c ->
                                AssistChip(onClick = {}, label = { Text("${c.str("action")} ${c.str("cible") ?: ""}") })
                            }
                        }
                    }
                }
            }
            val verdicts = data.list("suivi_verdicts")
            if (verdicts.isNotEmpty()) {
                item {
                    SectionCard("Suivi des verdicts") {
                        Muted("Cours depuis chaque verdict : pour voir ce qui s'est révélé juste ou faux.")
                        verdicts.take(15).forEach { v ->
                            val since = v.num("since") ?: v.num("depuis")
                            InfoRow(
                                "${v.str("nom") ?: v.str("isin")} · ${v.str("verdict") ?: ""}",
                                pct(since), tone = since, sub = day(v.str("date")),
                            )
                        }
                    }
                }
            }
        }
    }
}

/** One analysis in full: market, lines with their verdicts, ideas, advice, sources. */
@Composable
fun AnalyseScreen(id: Int, nav: NavController, onBack: () -> Unit) {
    val state = rememberCall("analyse", Engine.args("id" to id), id)
    ScreenScaffold("Analyse", onBack = onBack) { padding ->
        CallScreen(state, padding) { data ->
            val a = data.objOrNull("analyse") ?: JSONObject()
            val facts = data.objOrNull("lignes") ?: JSONObject()
            item {
                SectionCard {
                    Muted("${kindLabel(data.str("type"))} du ${day(data.str("seance"))} · ton ${a.str("ton") ?: "—"}")
                    Text(a.str("titre") ?: "Analyse", style = MaterialTheme.typography.headlineSmall,
                        fontWeight = FontWeight.SemiBold)
                    a.strings("points_cles").forEach { Text("• $it") }
                    data.objOrNull("patrimoine")?.num("effet_marche_eur")?.let {
                        InfoRow("Effet du marché sur tes titres", euros(it, sign = true), tone = it)
                    }
                }
            }
            a.objOrNull("marche")?.let { m ->
                item {
                    SectionCard("Marché") {
                        m.str("resume")?.let { Text(it) }
                        m.list("themes").forEach { t ->
                            Text(t.str("titre") ?: "", fontWeight = FontWeight.SemiBold)
                            t.str("detail")?.let { Text(it, style = MaterialTheme.typography.bodyMedium) }
                        }
                    }
                }
            }
            val lines = a.list("lignes")
            if (lines.isNotEmpty()) {
                item {
                    SectionCard("Tes lignes") {
                        lines.forEach { l ->
                            val f = facts.objOrNull(l.str("isin") ?: "")
                            val move = f?.num("move")
                            InfoRow(f?.str("nom") ?: l.str("isin") ?: "", pct(move), tone = move,
                                sub = "${l.str("verdict") ?: ""} · confiance ${l.str("confiance") ?: "—"}")
                            l.str("cause")?.let { Text(it, style = MaterialTheme.typography.bodyMedium) }
                            l.str("these")?.let { Muted("Thèse : $it") }
                            l.str("action")?.let { Text("À faire : $it", color = MaterialTheme.colorScheme.primary) }
                        }
                    }
                }
            }
            val advice = a.list("conseils")
            if (advice.isNotEmpty()) {
                item {
                    SectionCard("Conseils") {
                        Muted("Claude ne passe aucun ordre : à toi de décider et d'exécuter dans Trade Republic.")
                        advice.forEach { c ->
                            val size = listOfNotNull(c.num("montant_eur")?.let { euros(it) },
                                c.num("prix_limite")?.let { "limite " + euros(it, cents = true) }).joinToString(" · ")
                            Text("${c.str("action")} ${c.str("cible") ?: ""}" + if (size.isNotEmpty()) " · $size" else "",
                                fontWeight = FontWeight.SemiBold, color = gainColor(
                                    when (c.str("action")) { "acheter", "renforcer" -> 1.0; "alléger", "vendre" -> -1.0; else -> null }))
                            c.str("pourquoi")?.let { Text(it, style = MaterialTheme.typography.bodyMedium) }
                            c.str("risque")?.let { Muted("Risque : $it") }
                            c.str("invalidation")?.let { Muted("Invalidé si : $it") }
                            Muted("Horizon ${c.str("horizon") ?: "—"} · confiance ${c.str("confiance") ?: "—"}")
                        }
                    }
                }
            }
            val ideas = a.list("idees")
            if (ideas.isNotEmpty()) {
                item {
                    SectionCard("Idées à creuser") {
                        ideas.forEach { i ->
                            Text(i.str("nom") ?: "", fontWeight = FontWeight.SemiBold)
                            i.str("these")?.let { Text(it, style = MaterialTheme.typography.bodyMedium) }
                            i.str("risque")?.let { Muted("Risque : $it") }
                        }
                    }
                }
            }
            val sources = a.list("sources")
            if (sources.isNotEmpty()) {
                item {
                    val uri = LocalUriHandler.current
                    SectionCard("Sources") {
                        sources.forEach { s ->
                            Text("[${s.str("id") ?: s.int("id") ?: ""}] ${s.str("titre") ?: s.str("url")}",
                                style = MaterialTheme.typography.bodySmall,
                                textDecoration = TextDecoration.Underline,
                                modifier = Modifier.clickable(enabled = s.str("url") != null) {
                                    s.str("url")?.let { u -> runCatching { uri.openUri(u) } }
                                })
                        }
                    }
                }
            }
        }
    }
}
