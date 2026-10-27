package fr.julesgourio.patrimoine.work

import android.content.Context
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.OutOfQuotaPolicy
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import java.time.Duration
import java.time.LocalDateTime
import java.time.LocalTime
import java.util.concurrent.TimeUnit

object Scheduler {
    const val DAILY = "synchro-quotidienne"
    const val NOW = "synchro-maintenant"
    private const val ANALYSES = "analyses-cloud"
    private const val VEILLE = "veille-prix"
    private val SYNC_TIME: LocalTime = LocalTime.of(7, 30)

    private val network = Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build()

    /** Daily sync around 7:30 and a price watch every 30 minutes (price alerts); kept as they are if already planned. */
    fun ensure(context: Context) {
        val wm = WorkManager.getInstance(context)
        val daily = PeriodicWorkRequestBuilder<SyncWorker>(24, TimeUnit.HOURS)
            .setInitialDelay(untilNext(SYNC_TIME))
            .setConstraints(network)
            .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 15, TimeUnit.MINUTES)
            .build()
        wm.enqueueUniquePeriodicWork(DAILY, ExistingPeriodicWorkPolicy.KEEP, daily)
        wm.cancelUniqueWork(ANALYSES)  // analyses are on demand now: no more cloud routines to collect
        val veille = PeriodicWorkRequestBuilder<VeilleWorker>(30, TimeUnit.MINUTES).setConstraints(network).build()
        wm.enqueueUniquePeriodicWork(VEILLE, ExistingPeriodicWorkPolicy.KEEP, veille)
    }

    /** « Synchroniser » button: as soon as possible, still finishing if the app is closed meanwhile. */
    fun syncNow(context: Context) {
        val request = OneTimeWorkRequestBuilder<SyncWorker>()
            .setExpedited(OutOfQuotaPolicy.RUN_AS_NON_EXPEDITED_WORK_REQUEST)
            .setConstraints(network)
            .build()
        WorkManager.getInstance(context).enqueueUniqueWork(NOW, ExistingWorkPolicy.KEEP, request)
    }

    private fun untilNext(time: LocalTime): Duration {
        val now = LocalDateTime.now()
        var next = now.toLocalDate().atTime(time)
        if (!next.isAfter(now)) next = next.plusDays(1)
        return Duration.between(now, next)
    }
}
