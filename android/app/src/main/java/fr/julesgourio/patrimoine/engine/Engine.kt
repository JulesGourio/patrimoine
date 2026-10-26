package fr.julesgourio.patrimoine.engine

import android.content.Context
import com.chaquo.python.PyObject
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.File

/**
 * The Python engine (`patrimoine.mobile`), started once per process on first use.
 * Every call runs off the main thread and comes back as a [Reply]; nothing here can place an order.
 */
object Engine {
    private lateinit var context: Context
    private val startLock = Mutex()

    @Volatile
    private var module: PyObject? = null

    fun attach(context: Context) {
        this.context = context.applicationContext
    }

    val dataDir: File get() = File(context.filesDir, "data")
    val cacheDir: File get() = context.cacheDir

    private suspend fun mobile(): PyObject = module ?: startLock.withLock {
        module ?: run {
            if (!Python.isStarted()) Python.start(AndroidPlatform(context))
            val m = Python.getInstance().getModule("patrimoine.mobile")
            val reply = Reply.parse(
                m.callAttr("init", dataDir.absolutePath, SecretStore(context), Notifier(context)).toString(),
            )
            if (reply is Reply.Err) throw IllegalStateException("démarrage du moteur : ${reply.message}")
            m.also { module = it }
        }
    }

    private suspend fun invoke(function: String, vararg args: Any?): Reply = withContext(Dispatchers.IO) {
        try {
            Reply.parse(mobile().callAttr(function, *args).toString())
        } catch (e: Throwable) {
            Reply.Err(e.message ?: e.toString())
        }
    }

    /** A tool of `patrimoine.api` or a screen of `patrimoine.mobile`, by name. */
    suspend fun call(name: String, args: JSONObject = JSONObject()): Reply = invoke("call", name, args.toString())

    /** `args("jours" to 30)`: keyword arguments for [call]. */
    fun args(vararg pairs: Pair<String, Any?>): JSONObject =
        JSONObject().apply { pairs.forEach { (k, v) -> put(k, v ?: JSONObject.NULL) } }

    suspend fun sync(): Reply = invoke("sync")
    suspend fun pullAnalyses(): Reply = invoke("pull_analyses")
    suspend fun importFile(kind: String, path: String): Reply = invoke("import_file", kind, path)
    suspend fun exportDatabase(dest: String): Reply = invoke("export_database", dest)
    suspend fun setBalance(account: String, amount: String): Reply = invoke("set_balance", account, amount)
    suspend fun setSecret(name: String, value: String): Reply = invoke("set_secret", name, value)
    suspend fun trLogin(): Reply = invoke("tr_login")
    suspend fun cmbConsentUrl(): Reply = invoke("cmb_consent_url")
    suspend fun cmbConsentFinish(url: String): Reply = invoke("cmb_consent_finish", url)
    suspend fun testNotification(): Reply = invoke("test_notification")
}
