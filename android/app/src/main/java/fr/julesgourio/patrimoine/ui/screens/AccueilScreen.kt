package fr.julesgourio.patrimoine.ui.screens

import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Sync
import androidx.compose.material3.Button
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.text.font.FontWeight
import androidx.navigation.NavController
import fr.julesgourio.patrimoine.ui.Routes
import fr.julesgourio.patrimoine.ui.components.BigFigure
import fr.julesgourio.patrimoine.ui.components.CallScreen
import fr.julesgourio.patrimoine.ui.components.InfoRow
import fr.julesgourio.patrimoine.ui.components.LineChart
import fr.julesgourio.patrimoine.ui.components.LocalSync
import fr.julesgourio.patrimoine.ui.components.Muted
import fr.julesgourio.patrimoine.ui.components.ScreenScaffold
import fr.julesgourio.patrimoine.ui.components.SectionCard
import fr.julesgourio.patrimoine.ui.components.euros
import fr.julesgourio.patrimoine.ui.components.int
import fr.julesgourio.patrimoine.ui.components.moment
import fr.julesgourio.patrimoine.ui.components.num
import fr.julesgourio.patrimoine.ui.components.numbers
import fr.julesgourio.patrimoine.ui.components.objOrNull
import fr.julesgourio.patrimoine.ui.components.rememberCall
import fr.julesgourio.patrimoine.ui.components.str
import fr.julesgourio.patrimoine.ui.components.strings
import org.json.JSONArray

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
            item {
                val v30 = p.num("variation_30j")
                val v1y = p.num("variation_1an")
                SectionCard {
                    BigFigure(
                        caption = "Patrimoine total au " + fr.julesgourio.patrimoine.ui.components.day(p.str("date")),
                        value = euros(total),
                        detail = "30 jours ${euros(v30, sign = true)} · 1 an ${euros(v1y, sign = true)}",
                        tone = v30,
                    )
                    LineChart(curve(data.optJSONArray("courbe")))
                    Muted("Avant impôts. ${p.str("limites") ?: ""}")
                }
            }
            item {
                SectionCard("Par compte") {
                    p.objOrNull("comptes")?.numbers()?.sortedByDescending { it.second }?.forEach { (name, value) ->
                        InfoRow(name, euros(value))
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
                        Muted("Séance du " + fr.julesgourio.patrimoine.ui.components.day(a.str("seance")))
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
