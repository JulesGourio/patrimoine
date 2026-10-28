package fr.julesgourio.patrimoine.work

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import fr.julesgourio.patrimoine.engine.Engine
import fr.julesgourio.patrimoine.engine.Reply
import org.json.JSONObject

/** Other investors and radar, at night, silently (no foreground banner): never while Jules uses the app. */
class HeavySyncWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result {
        val reply = Engine.syncLourd()
        val busy = ((reply as? Reply.Ok)?.data as? JSONObject)?.optBoolean("deja_en_cours") == true
        return if (busy && runAttemptCount < 3) Result.retry() else Result.success()
    }
}
