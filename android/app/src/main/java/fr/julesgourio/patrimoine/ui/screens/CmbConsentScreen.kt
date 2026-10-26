package fr.julesgourio.patrimoine.ui.screens

import android.annotation.SuppressLint
import android.content.Intent
import android.net.Uri
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import fr.julesgourio.patrimoine.engine.Engine
import fr.julesgourio.patrimoine.engine.Reply
import fr.julesgourio.patrimoine.ui.components.ErrorBox
import fr.julesgourio.patrimoine.ui.components.Muted
import fr.julesgourio.patrimoine.ui.components.ScreenScaffold
import fr.julesgourio.patrimoine.ui.components.str
import kotlinx.coroutines.launch
import org.json.JSONObject

/**
 * Renewing the CMB access (every 180 days): the bank's sign-in page in a web view; when the bank sends Jules
 * back to the redirect address (https://localhost/patrimoine?code=…) the app catches it and finishes the
 * consent, no copy and paste. If the bank opens its own app for the confirmation, it comes back here after.
 */
@SuppressLint("SetJavaScriptEnabled")
@Composable
fun CmbConsentScreen(onBack: () -> Unit) {
    val scope = rememberCoroutineScope()
    var url by remember { mutableStateOf<String?>(null) }
    var redirect by remember { mutableStateOf("https://localhost/patrimoine") }
    var error by remember { mutableStateOf<String?>(null) }
    var done by remember { mutableStateOf<String?>(null) }
    var pasted by remember { mutableStateOf("") }

    fun finish(address: String) {
        scope.launch {
            when (val r = Engine.cmbConsentFinish(address)) {
                is Reply.Ok -> done = "Accès CMB renouvelé (${(r.data as? JSONObject)?.optInt("comptes") ?: 0} compte(s))."
                is Reply.Err -> error = r.message
            }
        }
    }

    LaunchedEffect(Unit) {
        when (val r = Engine.cmbConsentUrl()) {
            is Reply.Ok -> (r.data as? JSONObject)?.let { d ->
                url = d.str("url")
                d.str("retour")?.let { redirect = it }
            }
            is Reply.Err -> error = r.message
        }
    }

    ScreenScaffold("Accès CMB", onBack = onBack) { padding ->
        Column(Modifier.fillMaxSize().padding(padding)) {
            when {
                done != null -> Column(Modifier.padding(16.dp)) {
                    Text(done!!)
                    Button(onClick = onBack) { Text("Terminé") }
                }
                error != null -> ErrorBox(error!!) { error = null; onBack() }
                url == null -> CircularProgressIndicator(Modifier.padding(32.dp))
                else -> {
                    AndroidView(
                        modifier = Modifier.weight(1f).fillMaxWidth(),
                        factory = { ctx ->
                            WebView(ctx).apply {
                                settings.javaScriptEnabled = true
                                settings.domStorageEnabled = true
                                webViewClient = object : WebViewClient() {
                                    override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                                        val target = request.url.toString()
                                        if (target.startsWith(redirect)) {
                                            finish(target)
                                            return true
                                        }
                                        if (request.url.scheme !in listOf("http", "https")) {
                                            // The bank's app (strong authentication): open it, then come back here.
                                            runCatching { ctx.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(target))) }
                                            return true
                                        }
                                        return false
                                    }
                                }
                                loadUrl(url!!)
                            }
                        },
                    )
                    Column(Modifier.padding(12.dp)) {
                        Muted("Si la page reste bloquée à la fin, colle ici l'adresse https://localhost/patrimoine?code=…")
                        OutlinedTextField(value = pasted, onValueChange = { pasted = it }, singleLine = true,
                            modifier = Modifier.fillMaxWidth(), label = { Text("Adresse de retour") })
                        Button(onClick = { finish(pasted) }, enabled = pasted.contains("code=")) { Text("Valider") }
                    }
                }
            }
        }
    }
}
