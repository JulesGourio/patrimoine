package fr.julesgourio.patrimoine.ui.screens

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import fr.julesgourio.patrimoine.engine.Engine
import fr.julesgourio.patrimoine.engine.Reply
import fr.julesgourio.patrimoine.ui.components.CallScreen
import fr.julesgourio.patrimoine.ui.components.Muted
import fr.julesgourio.patrimoine.ui.components.ScreenScaffold
import fr.julesgourio.patrimoine.ui.components.SectionCard
import fr.julesgourio.patrimoine.ui.components.day
import fr.julesgourio.patrimoine.ui.components.euros
import fr.julesgourio.patrimoine.ui.components.gainColor
import fr.julesgourio.patrimoine.ui.components.int
import fr.julesgourio.patrimoine.ui.components.list
import fr.julesgourio.patrimoine.ui.components.num
import fr.julesgourio.patrimoine.ui.components.number
import fr.julesgourio.patrimoine.ui.components.rememberCall
import fr.julesgourio.patrimoine.ui.components.str
import kotlinx.coroutines.launch
import org.json.JSONObject

/** Orders Claude prepared (`ordres_proposes`): shown and noted (`statut_ordre`) here, never sent from the app. */
private val ORDER_STATUSES = listOf("proposé" to "Proposés", "passé" to "Passés", "abandonné" to "Abandonnés", "" to "Tous")

private fun accountLabel(id: String?): String = when (id) {
    "tr_cto" -> "Trade Republic CTO"
    "tr_pea" -> "Trade Republic PEA"
    null -> "compte non précisé"
    else -> id
}

@Composable
fun OrdresScreen(onBack: () -> Unit) {
    var status by remember { mutableStateOf("proposé") }
    var message by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()
    val state = rememberCall("ordres_proposes", Engine.args("statut" to status), status)

    ScreenScaffold("Ordres préparés", onBack = onBack) { padding ->
        Column(Modifier.fillMaxSize().padding(padding)) {
            Surface(color = MaterialTheme.colorScheme.secondaryContainer, modifier = Modifier.fillMaxWidth()) {
                Text(
                    "L'appli ne passe jamais d'ordre : elle l'affiche, tu l'exécutes toi-même dans Trade Republic.",
                    Modifier.padding(horizontal = 16.dp, vertical = 10.dp),
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSecondaryContainer,
                )
            }
            Box(Modifier.weight(1f).fillMaxWidth()) {
                CallScreen(state) { data ->
                    item {
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            ORDER_STATUSES.forEach { (value, label) ->
                                FilterChip(
                                    selected = status == value,
                                    onClick = { status = value; message = null },
                                    label = { Text(label) },
                                )
                            }
                        }
                    }
                    message?.let {
                        item { Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodyMedium) }
                    }
                    val ordres = data.list("ordres")
                    if (ordres.isEmpty()) item { Muted("Aucun ordre dans cette liste.") }
                    items(ordres, key = { it.int("id") ?: it.hashCode() }) { o ->
                        OrderCard(o) { id, nouveau ->
                            scope.launch {
                                when (val r = Engine.call("statut_ordre", Engine.args("id" to id, "statut" to nouveau))) {
                                    is Reply.Ok -> { message = null; state.reload() }
                                    is Reply.Err -> message = r.message
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun OrderCard(o: JSONObject, setStatus: (id: Int, statut: String) -> Unit) {
    val id = o.int("id")
    val achat = o.str("side") == "achat"
    val statut = o.str("status")
    var open by remember { mutableStateOf(false) }
    val context = LocalContext.current
    val quantite = o.num("quantity")
    val montant = o.num("amount_eur")
    val limite = o.num("limit_price")
    SectionCard {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                if (achat) "ACHAT" else "VENTE",
                Modifier.padding(end = 8.dp),
                style = MaterialTheme.typography.labelLarge,
                fontWeight = FontWeight.Bold,
                color = gainColor(if (achat) 1.0 else -1.0),
            )
            Text(
                o.str("name") ?: o.str("isin") ?: "—",
                Modifier.weight(1f),
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold,
            )
            if (statut != null && statut != "proposé") Muted(statut)
        }
        Muted(accountLabel(o.str("account_id")) + " · préparé le " + day(o.str("created_at")))
        val taille = listOfNotNull(
            quantite?.let { "${number(it, 4)} titres" },
            montant?.let { euros(it) },
        ).joinToString(" ou ")
        if (taille.isNotEmpty()) Text(taille, style = MaterialTheme.typography.bodyLarge)
        Text(
            if (limite != null) "Limite : ${euros(limite, cents = true)}" else "Sans limite de prix",
            style = MaterialTheme.typography.bodyMedium,
        )
        TextButton(onClick = { open = !open }) { Text(if (open) "Masquer" else "Justification et risques") }
        if (open) {
            Text("Justification", style = MaterialTheme.typography.labelLarge)
            Text(o.str("rationale") ?: "—", style = MaterialTheme.typography.bodyMedium)
            Text("Risques", style = MaterialTheme.typography.labelLarge)
            Text(o.str("risks") ?: "—", style = MaterialTheme.typography.bodyMedium)
        }
        OutlinedButton(onClick = { copyToClipboard(context, orderText(o)) }) { Text("Copier l'ordre") }
        if (id != null && statut == "proposé") {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = { setStatus(id, "passé") }) { Text("Je l'ai passé") }
                OutlinedButton(onClick = { setStatus(id, "abandonné") }) { Text("Abandonner") }
            }
        }
    }
}

/** The order as plain text, to paste into a note or check against Trade Republic. */
private fun orderText(o: JSONObject): String {
    val taille = listOfNotNull(
        o.num("quantity")?.let { "${number(it, 4)} titres" },
        o.num("amount_eur")?.let { euros(it) },
    ).joinToString(" ou ")
    return listOfNotNull(
        "${if (o.str("side") == "achat") "ACHAT" else "VENTE"} ${o.str("name") ?: o.str("isin") ?: "—"}" +
            (o.str("isin")?.let { " ($it)" } ?: ""),
        "Compte : ${accountLabel(o.str("account_id"))}",
        taille.takeIf { it.isNotEmpty() }?.let { "Quantité : $it" },
        o.num("limit_price")?.let { "Limite : ${euros(it, cents = true)}" } ?: "Sans limite de prix",
        "Justification : ${o.str("rationale") ?: "—"}",
        "Risques : ${o.str("risks") ?: "—"}",
    ).joinToString("\n")
}

private fun copyToClipboard(context: Context, text: String) {
    val cm = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
    cm.setPrimaryClip(ClipData.newPlainText("Ordre", text))
}
