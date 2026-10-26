package fr.julesgourio.patrimoine.ui.screens

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
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
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.navigation.NavController
import fr.julesgourio.patrimoine.engine.Engine
import fr.julesgourio.patrimoine.engine.Files
import fr.julesgourio.patrimoine.engine.Reply
import fr.julesgourio.patrimoine.ui.Routes
import fr.julesgourio.patrimoine.ui.components.CallScreen
import fr.julesgourio.patrimoine.ui.components.InfoRow
import fr.julesgourio.patrimoine.ui.components.LocalSync
import fr.julesgourio.patrimoine.ui.components.Muted
import fr.julesgourio.patrimoine.ui.components.ScreenScaffold
import fr.julesgourio.patrimoine.ui.components.SectionCard
import fr.julesgourio.patrimoine.ui.components.bool
import fr.julesgourio.patrimoine.ui.components.day
import fr.julesgourio.patrimoine.ui.components.moment
import fr.julesgourio.patrimoine.ui.components.objOrNull
import fr.julesgourio.patrimoine.ui.components.rememberCall
import fr.julesgourio.patrimoine.ui.components.str
import fr.julesgourio.patrimoine.ui.components.strings
import kotlinx.coroutines.launch
import java.io.File
import java.time.LocalDate

/** Secrets the app asks for, in the order Jules needs them. Names are those of `patrimoine.vault.KNOWN`. */
private val SECRETS = listOf(
    Triple("tr_phone", "Téléphone Trade Republic", KeyboardType.Phone),
    Triple("tr_pin", "PIN Trade Republic (4 chiffres)", KeyboardType.NumberPassword),
    Triple("github_token", "Jeton GitHub (analyses Claude)", KeyboardType.Password),
    Triple("smtp_password", "Mot de passe d'application Gmail (mails)", KeyboardType.Password),
    Triple("ntfy_topic", "Sujet ntfy (facultatif sur le téléphone)", KeyboardType.Password),
)

@Composable
fun ReglagesScreen(nav: NavController, onBack: () -> Unit) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val sync = LocalSync.current
    val state = rememberCall("etat")
    val refs = rememberCall("references")
    var message by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf<String?>(null) }

    fun run(label: String, block: suspend () -> Reply) {
        busy = label
        scope.launch {
            message = when (val r = block()) {
                is Reply.Ok -> "$label : fait." + (r.data?.let { " $it" }?.take(300) ?: "")
                is Reply.Err -> "$label : ${r.message}"
            }
            busy = null
            state.reload()
        }
    }

    // Imports: the picked file is copied into the cache under its own name, then handed to the engine.
    fun importer(kind: String, label: String, fallback: String) =
        { uri: android.net.Uri? ->
            if (uri != null) run(label) {
                val file = try {
                    Files.toCache(context, uri, fallback)
                } catch (e: Exception) {
                    return@run Reply.Err(e.message ?: "fichier illisible")
                }
                Engine.importFile(kind, file.absolutePath)
            }
        }

    val pickPeg = rememberLauncherForActivityResult(ActivityResultContracts.OpenMultipleDocuments()) { uris ->
        uris.forEach { importer("peg", "Relevé Amundi", "AVO.pdf")(it) }
    }
    val pickCsv = rememberLauncherForActivityResult(ActivityResultContracts.OpenMultipleDocuments()) { uris ->
        uris.forEach { importer("cmb_csv", "Export CMB", "RELEVE_import.csv")(it) }
    }
    val pickKey = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument(),
        importer("cle_cmb", "Clé Enable Banking", "cle.pem"))
    var confirmBase by remember { mutableStateOf(false) }
    val pickBase = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument(),
        importer("base", "Import de la base", "patrimoine.db"))
    val saveBase = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("application/octet-stream")) { uri ->
        if (uri != null) run("Sauvegarde") {
            val tmp = File(context.cacheDir, "export/patrimoine.db")
            when (val r = Engine.exportDatabase(tmp.absolutePath)) {
                is Reply.Ok -> try {
                    Files.copyToUri(context, tmp, uri)
                    Reply.Ok("enregistrée")
                } catch (e: Exception) {
                    Reply.Err(e.message ?: "écriture impossible")
                } finally {
                    tmp.delete()
                }
                is Reply.Err -> r
            }
        }
    }

    ScreenScaffold("Réglages", onBack = onBack) { padding ->
        CallScreen(state, padding) { s ->
            item {
                if (busy != null) SectionCard { Text("$busy…") }
                message?.let { SectionCard { Text(it) } }
            }
            item {
                SectionCard("Synchronisation") {
                    InfoRow("Dernière", moment(s.str("derniere_synchro")))
                    InfoRow("Opérations en base", s.optInt("operations").toString())
                    Muted("Chaque matin vers 7 h 30, et les analyses Claude toutes les heures.")
                    Button(onClick = sync.start, enabled = !sync.running) {
                        Text(if (sync.running) "Synchronisation en cours…" else "Synchroniser maintenant")
                    }
                }
            }
            item {
                SectionCard("Trade Republic") {
                    InfoRow("Session", if (s.bool("trade_republic_session")) "enregistrée" else "à ouvrir")
                    Muted("Renseigne le téléphone et le PIN ci-dessous, puis connecte-toi : confirme dans l'appli " +
                        "Trade Republic (2 minutes au plus). Lecture seule : aucun ordre n'est jamais passé.")
                    Button(onClick = { run("Connexion Trade Republic") { Engine.trLogin() } }, enabled = busy == null) {
                        Text("Se connecter")
                    }
                }
            }
            item {
                SectionCard("CMB (Enable Banking)") {
                    InfoRow("Clé de l'application", if (s.bool("cmb_cle")) "installée" else "absente")
                    InfoRow("Accès valable jusqu'au", day(s.str("cmb_acces_jusqu_au")))
                    Muted("La clé .pem de l'application Enable Banking est dans data/enablebanking/ sur le PC.")
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        OutlinedButton(onClick = { pickKey.launch(arrayOf("*/*")) }) { Text("Installer la clé") }
                        Button(onClick = { nav.navigate(Routes.CMB) }, enabled = s.bool("cmb_cle")) {
                            Text("Renouveler l'accès")
                        }
                    }
                }
            }
            item {
                SectionCard("Secrets") {
                    Muted("Chiffrés par l'Android Keystore, jamais écrits en clair.")
                    val defined = s.objOrNull("secrets")
                    SECRETS.forEach { (name, label, keyboard) ->
                        SecretField(name, label, keyboard, defined?.bool(name) == true) { value ->
                            run(label) { Engine.setSecret(name, value) }
                        }
                    }
                }
            }
            item {
                SectionCard("Livrets (soldes saisis)") {
                    Muted("La CMB ne partage pas les livrets : saisis le solde après les intérêts ou un versement.")
                    val accounts = (refs.load as? fr.julesgourio.patrimoine.ui.components.Load.Done)
                        ?.data?.strings("comptes_solde_manuel") ?: emptyList()
                    BalanceEntry(accounts) { account, amount -> run("Solde $account") { Engine.setBalance(account, amount) } }
                }
            }
            item {
                SectionCard("Imports") {
                    Muted("Base du PC : copie data/patrimoine.db sur le téléphone (Drive, câble…) puis importe-la. " +
                        "La base actuelle du téléphone est gardée à côté.")
                    Button(onClick = { confirmBase = true }, enabled = !sync.running) { Text("Importer une base") }
                    OutlinedButton(onClick = { pickPeg.launch(arrayOf("application/pdf")) }) { Text("Relevés Amundi (PEG, AVO*.pdf)") }
                    OutlinedButton(onClick = { pickCsv.launch(arrayOf("text/*", "application/vnd.ms-excel", "*/*")) }) {
                        Text("Exports CMB (RELEVE_*.csv)")
                    }
                }
            }
            item {
                SectionCard("Sauvegarde") {
                    Muted("Une copie complète de la base, à garder ailleurs (Drive) ou à rapporter sur le PC.")
                    Button(onClick = { saveBase.launch("patrimoine-${LocalDate.now()}.db") }) { Text("Enregistrer une copie") }
                }
            }
            item {
                SectionCard("Notifications") {
                    Button(onClick = { run("Notification de test") { Engine.testNotification() } }) { Text("Tester") }
                }
            }
        }
    }

    if (confirmBase) {
        AlertDialog(
            onDismissRequest = { confirmBase = false },
            title = { Text("Remplacer la base du téléphone ?") },
            text = { Text("Elle sera remplacée par le fichier choisi ; l'actuelle est gardée en copie datée.") },
            confirmButton = {
                TextButton(onClick = { confirmBase = false; pickBase.launch(arrayOf("*/*")) }) { Text("Choisir le fichier") }
            },
            dismissButton = { TextButton(onClick = { confirmBase = false }) { Text("Annuler") } },
        )
    }
}

@Composable
private fun SecretField(name: String, label: String, keyboard: KeyboardType, defined: Boolean, save: (String) -> Unit) {
    var value by remember(name) { mutableStateOf("") }
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        OutlinedTextField(
            value = value,
            onValueChange = { value = it },
            label = { Text(label) },
            placeholder = { Text(if (defined) "défini (laisser vide pour garder)" else "non défini") },
            singleLine = true,
            visualTransformation = if (name == "tr_phone") androidx.compose.ui.text.input.VisualTransformation.None
            else PasswordVisualTransformation(),
            keyboardOptions = KeyboardOptions(keyboardType = keyboard),
            modifier = Modifier.weight(1f),
        )
        TextButton(onClick = { save(value); value = "" }, enabled = value.isNotBlank()) { Text("OK") }
    }
    if (defined) {
        TextButton(onClick = { save("") }) {
            Text("Effacer", color = MaterialTheme.colorScheme.error)
        }
    }
}

@Composable
private fun BalanceEntry(accounts: List<String>, save: (String, String) -> Unit) {
    var account by remember(accounts) { mutableStateOf(accounts.firstOrNull()) }
    var amount by remember { mutableStateOf("") }
    var open by remember { mutableStateOf(false) }
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        OutlinedButton(onClick = { open = true }) { Text(account ?: "compte") }
        DropdownMenu(expanded = open, onDismissRequest = { open = false }) {
            accounts.forEach { a -> DropdownMenuItem(text = { Text(a) }, onClick = { account = a; open = false }) }
        }
        OutlinedTextField(
            value = amount, onValueChange = { amount = it }, label = { Text("Solde en €") }, singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal), modifier = Modifier.weight(1f),
        )
    }
    Button(onClick = { account?.let { save(it, amount); amount = "" } }, enabled = account != null && amount.isNotBlank()) {
        Text("Enregistrer le solde")
    }
}
