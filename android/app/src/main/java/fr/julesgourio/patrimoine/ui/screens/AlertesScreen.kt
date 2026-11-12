package fr.julesgourio.patrimoine.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import fr.julesgourio.patrimoine.engine.Engine
import fr.julesgourio.patrimoine.engine.Reply
import fr.julesgourio.patrimoine.ui.components.CallScreen
import fr.julesgourio.patrimoine.ui.components.Muted
import fr.julesgourio.patrimoine.ui.components.ScreenScaffold
import fr.julesgourio.patrimoine.ui.components.SectionCard
import fr.julesgourio.patrimoine.ui.components.euros
import fr.julesgourio.patrimoine.ui.components.int
import fr.julesgourio.patrimoine.ui.components.list
import fr.julesgourio.patrimoine.ui.components.moment
import fr.julesgourio.patrimoine.ui.components.num
import fr.julesgourio.patrimoine.ui.components.number
import fr.julesgourio.patrimoine.ui.components.rememberCall
import fr.julesgourio.patrimoine.ui.components.str
import kotlinx.coroutines.launch

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
