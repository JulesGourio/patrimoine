package fr.julesgourio.patrimoine.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.navigation.NavController
import fr.julesgourio.patrimoine.engine.Engine
import fr.julesgourio.patrimoine.engine.Reply
import fr.julesgourio.patrimoine.ui.Routes
import fr.julesgourio.patrimoine.ui.components.CallScreen
import fr.julesgourio.patrimoine.ui.components.Load
import fr.julesgourio.patrimoine.ui.components.Muted
import fr.julesgourio.patrimoine.ui.components.ScreenScaffold
import fr.julesgourio.patrimoine.ui.components.SectionCard
import fr.julesgourio.patrimoine.ui.components.bool
import fr.julesgourio.patrimoine.ui.components.day
import fr.julesgourio.patrimoine.ui.components.euros
import fr.julesgourio.patrimoine.ui.components.gainColor
import fr.julesgourio.patrimoine.ui.components.int
import fr.julesgourio.patrimoine.ui.components.list
import fr.julesgourio.patrimoine.ui.components.moment
import fr.julesgourio.patrimoine.ui.components.num
import fr.julesgourio.patrimoine.ui.components.number
import fr.julesgourio.patrimoine.ui.components.pct
import fr.julesgourio.patrimoine.ui.components.rememberCall
import fr.julesgourio.patrimoine.ui.components.str
import fr.julesgourio.patrimoine.ui.components.usd
import kotlinx.coroutines.launch
import org.json.JSONObject

// ---------------------------------------------------------------------------------------------
// Investisseurs
// ---------------------------------------------------------------------------------------------

private val INVESTOR_TABS = listOf("Nouveautés", "Radar", "Fonds", "Élus")

@Composable
fun InvestisseursScreen(nav: NavController, onBack: () -> Unit) {
    var tab by remember { mutableIntStateOf(0) }
    ScreenScaffold("Investisseurs", onBack = onBack) { padding ->
        Column(Modifier.fillMaxSize().padding(padding)) {
            TabRow(selectedTabIndex = tab) {
                INVESTOR_TABS.forEachIndexed { i, label ->
                    Tab(selected = tab == i, onClick = { tab = i }, text = { Text(label, maxLines = 1) })
                }
            }
            Box(Modifier.weight(1f).fillMaxWidth()) {
                when (tab) {
                    0 -> NouveautesTab(nav)
                    1 -> RadarTab(nav)
                    2 -> FondsTab()
                    else -> ElusTab()
                }
            }
        }
    }
}

/** Small rounded label, e.g. « sur tes titres ». */
@Composable
private fun Tag(text: String) {
    Surface(shape = RoundedCornerShape(50), color = MaterialTheme.colorScheme.tertiaryContainer) {
        Text(
            text,
            Modifier.padding(horizontal = 8.dp, vertical = 2.dp),
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onTertiaryContainer,
        )
    }
}

private fun NavController.openTitre(ticker: String?) {
    if (!ticker.isNullOrBlank()) navigate(Routes.titre(ticker))
}

@Composable
private fun NouveautesTab(nav: NavController) {
    var mine by remember { mutableStateOf(false) }
    val state = rememberCall("nouveautes", Engine.args("jours" to 14, "mes_titres" to mine), mine)
    CallScreen(state) { data ->
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                FilterChip(selected = mine, onClick = { mine = !mine }, label = { Text("Mes titres") })
            }
        }
        val fil = data.list("fil")
        if (fil.isEmpty()) {
            item { Muted(if (mine) "Rien de nouveau sur tes titres ces 14 jours." else "Rien de nouveau ces 14 jours.") }
        }
        items(fil) { o ->
            val ticker = o.str("ticker")
            val isMine = o.bool("mine")
            val since = o.num("since")
            Card(
                onClick = { nav.openTitre(ticker) },
                enabled = ticker != null,
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(
                    containerColor = if (isMine) MaterialTheme.colorScheme.tertiaryContainer.copy(alpha = 0.35f)
                    else MaterialTheme.colorScheme.surfaceContainerLow,
                ),
            ) {
                Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(
                            listOfNotNull(o.str("kind"), o.str("who")).joinToString(" · "),
                            Modifier.weight(1f),
                            style = MaterialTheme.typography.labelLarge,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                        Text(day(o.str("date")), style = MaterialTheme.typography.labelMedium)
                    }
                    Text(
                        listOfNotNull(o.str("name"), ticker?.let { "($it)" }).joinToString(" "),
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.SemiBold,
                    )
                    o.str("what")?.let { Text(it, style = MaterialTheme.typography.bodyMedium) }
                    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        o.num("value_usd")?.let { Muted(usd(it)) }
                        o.str("op_date")?.let { Muted("opération du ${day(it)}") }
                        if (since != null) {
                            Text(
                                "depuis : ${pct(since)}",
                                style = MaterialTheme.typography.bodySmall,
                                color = gainColor(since),
                            )
                        }
                    }
                    if (isMine) {
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Tag("sur tes titres")
                            o.num("mine_eur")?.takeIf { it > 0 }?.let { Muted("chez toi : ${euros(it)}") }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun RadarTab(nav: NavController) {
    val state = rememberCall("radar", Engine.args("n" to 25))
    CallScreen(state) { data ->
        val idees = data.list("idees")
        if (idees.isEmpty()) item { Muted("Le radar est vide pour l'instant (il est recalculé à chaque synchronisation).") }
        data.str("calcule_le")?.let { item { Muted("Calculé le ${moment(it)}") } }
        items(idees) { o ->
            val ticker = o.str("ticker")
            val mineEur = o.num("mine_eur")
            val rating = o.num("rating")
            val upside = o.num("upside")
            SectionCard(onClick = if (ticker != null) ({ nav.openTitre(ticker) }) else null) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(
                            ticker ?: "—",
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.SemiBold,
                        )
                        o.str("name")?.let { Muted(it) }
                    }
                    o.num("score")?.let {
                        Text("score ${number(it, 1)}", style = MaterialTheme.typography.labelLarge)
                    }
                }
                o.str("why")?.let { Text(it, style = MaterialTheme.typography.bodyMedium) }
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    listOf("1 m" to o.num("r1m"), "3 m" to o.num("r3m"), "1 an" to o.num("r1y")).forEach { (label, v) ->
                        Text(
                            "$label ${pct(v)}",
                            style = MaterialTheme.typography.bodySmall,
                            color = gainColor(v),
                        )
                    }
                }
                if (rating != null || upside != null) {
                    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        if (rating != null) Muted("avis analystes ${number(rating, 1)}/5")
                        if (upside != null) {
                            Text(
                                "objectif ${pct(upside)}",
                                style = MaterialTheme.typography.bodySmall,
                                color = gainColor(upside),
                            )
                        }
                    }
                }
                if (mineEur != null && mineEur > 0) {
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Tag("sur tes titres")
                        Muted("chez toi : ${euros(mineEur)}" + (o.str("mine_via")?.let { " via $it" } ?: ""))
                    }
                }
            }
        }
        val ventes = data.list("ventes")
        if (ventes.isNotEmpty()) {
            item {
                SectionCard("Ce qu'ils vendent") {
                    ventes.forEach { v ->
                        val t = v.str("ticker")
                        Row(
                            Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                        ) {
                            TextButton(onClick = { nav.openTitre(t) }, enabled = t != null) {
                                Text(listOfNotNull(t, v.str("name")).joinToString(" · "), maxLines = 1)
                            }
                            v.int("net")?.let { Muted("$it vendeurs nets") }
                        }
                    }
                }
            }
        }
        item { Muted("Idées à creuser, pas des signaux d'achat.") }
    }
}

@Composable
private fun FondsTab() {
    val state = rememberCall("investisseurs")
    val perf = rememberCall("performance_fonds")
    val byFund: Map<String, JSONObject> = (perf.load as? Load.Done)?.data?.list("fonds")
        ?.mapNotNull { f -> f.str("cik")?.let { it to f } }?.toMap() ?: emptyMap()
    CallScreen(state) { data ->
        val fonds = data.list("investisseurs")
        if (fonds.isEmpty()) item { Muted("Aucun fonds suivi pour l'instant.") }
        items(fonds) { f ->
            val p = f.str("cik")?.let { byFund[it] }
            SectionCard(f.str("name")) {
                listOfNotNull(f.str("manager"), f.str("style")).joinToString(" · ").takeIf { it.isNotEmpty() }
                    ?.let { Muted(it) }
                Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                    Muted("13F au ${day(f.str("period"))}")
                    f.num("total_usd")?.let { Muted(usd(it)) }
                    f.int("positions")?.let { Muted("$it lignes") }
                }
                f.num("top10")?.let { Muted("10 premières lignes : ${pct(it, sign = false, digits = 0)} du portefeuille") }
                f.str("top3")?.let { Text("Principales : $it", style = MaterialTheme.typography.bodyMedium) }
                if (p != null) {
                    val excess = p.num("excess")
                    Text(
                        "Copie de ses lignes : ${pct(p.num("ret"))} contre ${pct(p.num("bench"))} pour le S&P 500" +
                            " (écart ${pct(excess)})",
                        style = MaterialTheme.typography.bodyMedium,
                        color = gainColor(excess),
                    )
                    p.num("annual")?.let { Muted("soit ${pct(it)} par an") }
                }
            }
        }
        item { Muted("Les 13F ont jusqu'à 45 jours de retard et ne montrent que les positions longues cotées aux États-Unis.") }
    }
}

@Composable
private fun ElusTab() {
    val state = rememberCall("elus", Engine.args("mois" to 24))
    CallScreen(state) { data ->
        val classement = data.list("classement")
        if (classement.isEmpty()) item { Muted("Aucune déclaration d'élu pour l'instant.") }
        items(classement) { e ->
            val excess = e.num("excess")
            SectionCard {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(
                            e.str("name") ?: "—",
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.SemiBold,
                        )
                        Muted(listOfNotNull(e.str("chamber"), e.str("state")).joinToString(" · "))
                    }
                    if (e.bool("followed")) Tag("suivi")
                }
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    Text(
                        "écart au S&P 500 : ${pct(excess)}",
                        style = MaterialTheme.typography.bodyMedium,
                        color = gainColor(excess),
                    )
                    Muted("rendement ${pct(e.num("ret"))}")
                }
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    e.int("buys")?.let { Muted("$it achats") }
                    e.num("hit_rate")?.let { Muted("${pct(it, sign = false, digits = 0)} gagnants") }
                }
                e.str("top")?.let { Text("Principaux achats : $it", style = MaterialTheme.typography.bodyMedium) }
            }
        }
        item { Muted("Déclarations jusqu'à 45 jours en retard, montants en fourchettes : une estimation, pas le rendement de leur compte.") }
    }
}

// ---------------------------------------------------------------------------------------------
// Alertes
// ---------------------------------------------------------------------------------------------

private val RULE_TYPES = listOf(
    "baisse_ligne" to "Une ligne baisse de X %",
    "hausse_ligne" to "Une ligne monte de X %",
    "baisse_portefeuille" to "Le portefeuille baisse de X %",
    "seuil_bas" to "Un titre passe sous X €",
    "seuil_haut" to "Un titre passe au-dessus de X €",
)

private fun ruleLabel(kind: String?): String =
    RULE_TYPES.firstOrNull { it.first == kind }?.second ?: when (kind) {
        "concentration" -> "Concentration d'une ligne"
        "budget" -> "Budget dépassé"
        else -> kind ?: "Règle"
    }

private fun isPriceRule(kind: String?) = kind == "seuil_bas" || kind == "seuil_haut"

@Composable
fun AlertesScreen(onBack: () -> Unit) {
    val state = rememberCall("alertes")
    val scope = rememberCoroutineScope()
    var message by remember { mutableStateOf<String?>(null) }
    var dialog by remember { mutableStateOf(false) }

    ScreenScaffold("Alertes", onBack = onBack) { padding ->
        Box(Modifier.fillMaxSize()) {
            CallScreen(state, padding) { data ->
                message?.let {
                    item { Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodyMedium) }
                }
                item {
                    val recentes = data.list("recentes")
                    SectionCard("Déclenchées ces 30 jours") {
                        if (recentes.isEmpty()) Muted("Aucune alerte récente.")
                        recentes.forEach { a ->
                            Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                                Muted(moment(a.str("triggered_at")))
                                Text(a.str("message") ?: "—", style = MaterialTheme.typography.bodyMedium)
                            }
                        }
                    }
                }
                val regles = data.list("regles").filter { it.int("active") == 1 }
                item {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(
                            "Règles actives",
                            Modifier.weight(1f),
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.SemiBold,
                        )
                        Button(onClick = { dialog = true }) { Text("Nouvelle règle") }
                    }
                }
                if (regles.isEmpty()) item { Muted("Aucune règle active.") }
                items(regles, key = { it.int("id") ?: it.hashCode() }) { r ->
                    val kind = r.str("kind")
                    val threshold = r.num("threshold")
                    val id = r.int("id")
                    SectionCard {
                        Text(ruleLabel(kind), style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
                        val seuil = threshold?.let { if (isPriceRule(kind)) euros(it) else number(it, 2) + " %" }
                        Text(
                            listOfNotNull(
                                seuil?.let { "seuil $it" },
                                r.int("window_days")?.let { if (isPriceRule(kind)) null else "sur $it j" },
                                r.str("isin"),
                                r.str("target"),
                            ).joinToString(" · "),
                            style = MaterialTheme.typography.bodyMedium,
                        )
                        r.str("note")?.let { Muted(it) }
                        if (id != null) {
                            TextButton(onClick = {
                                scope.launch {
                                    val args = Engine.args("type" to "", "seuil" to 0.0, "desactiver_id" to id)
                                    when (val res = Engine.call("regle_alerte", args)) {
                                        is Reply.Ok -> { message = null; state.reload() }
                                        is Reply.Err -> message = res.message
                                    }
                                }
                            }) { Text("Désactiver") }
                        }
                    }
                }
            }
        }
    }

    if (dialog) {
        NewRuleDialog(
            onDismiss = { dialog = false },
            onCreated = { dialog = false; message = null; state.reload() },
        )
    }
}

@Composable
private fun NewRuleDialog(onDismiss: () -> Unit, onCreated: () -> Unit) {
    val scope = rememberCoroutineScope()
    var kind by remember { mutableStateOf(RULE_TYPES.first().first) }
    var menu by remember { mutableStateOf(false) }
    var threshold by remember { mutableStateOf("") }
    var isin by remember { mutableStateOf("") }
    var days by remember { mutableStateOf("1") }
    var error by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    val price = isPriceRule(kind)

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Nouvelle règle") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Box {
                    OutlinedButton(onClick = { menu = true }, modifier = Modifier.fillMaxWidth()) {
                        Text(ruleLabel(kind), maxLines = 1)
                    }
                    DropdownMenu(expanded = menu, onDismissRequest = { menu = false }) {
                        RULE_TYPES.forEach { (value, label) ->
                            DropdownMenuItem(text = { Text(label) }, onClick = { kind = value; menu = false })
                        }
                    }
                }
                OutlinedTextField(
                    value = threshold,
                    onValueChange = { threshold = it },
                    label = { Text(if (price) "Seuil (€)" else "Seuil (%)") },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                    modifier = Modifier.fillMaxWidth(),
                )
                OutlinedTextField(
                    value = isin,
                    onValueChange = { isin = it.trim().uppercase() },
                    label = { Text(if (price) "ISIN (obligatoire)" else "ISIN (facultatif)") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                if (!price) {
                    OutlinedTextField(
                        value = days,
                        onValueChange = { days = it.filter(Char::isDigit) },
                        label = { Text("Sur combien de jours") },
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                        modifier = Modifier.fillMaxWidth(),
                    )
                }
                error?.let { Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall) }
            }
        },
        confirmButton = {
            Button(
                enabled = !busy,
                onClick = {
                    val value = threshold.replace(',', '.').toDoubleOrNull()
                    if (value == null || value <= 0) {
                        error = "Indique un seuil positif."
                    } else if (price && isin.isBlank()) {
                        error = "Un seuil de prix demande un ISIN."
                    } else {
                        error = null
                        busy = true
                        scope.launch {
                            val args = Engine.args(
                                "type" to kind,
                                "seuil" to value,
                                "isin" to isin,
                                "jours" to (if (price) 1 else (days.toIntOrNull()?.coerceAtLeast(1) ?: 1)),
                            )
                            when (val r = Engine.call("regle_alerte", args)) {
                                is Reply.Ok -> onCreated()
                                is Reply.Err -> { error = r.message; busy = false }
                            }
                        }
                    }
                },
            ) { Text("Créer") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Annuler") } },
    )
}
