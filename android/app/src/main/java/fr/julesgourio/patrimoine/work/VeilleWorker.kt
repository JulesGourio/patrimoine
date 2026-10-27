package fr.julesgourio.patrimoine.work

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import fr.julesgourio.patrimoine.engine.Engine

/** Price watch: prices, valuation and alert rules only (Python skips it outside market hours). */
class VeilleWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result {
        Engine.veille()
        try {
            WidgetRefresh.run(applicationContext)
        } catch (e: Exception) {
            // the widget is optional: never fail the price watch for it
        }
        return Result.success()
    }
}
