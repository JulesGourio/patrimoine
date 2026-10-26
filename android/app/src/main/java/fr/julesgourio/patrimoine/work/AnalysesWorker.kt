package fr.julesgourio.patrimoine.work

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import fr.julesgourio.patrimoine.engine.Engine
import fr.julesgourio.patrimoine.engine.Reply

/** Publishes the analyses the Claude cloud routines pushed to GitHub (the PC does it every 15 minutes). */
class AnalysesWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result = when (Engine.pullAnalyses()) {
        is Reply.Ok -> Result.success()
        is Reply.Err -> Result.retry()
    }
}
