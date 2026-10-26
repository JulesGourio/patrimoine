package fr.julesgourio.patrimoine.engine

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import fr.julesgourio.patrimoine.R
import fr.julesgourio.patrimoine.ui.MainActivity
import java.util.concurrent.atomic.AtomicInteger

/** The phone's notifications, used by `patrimoine.notify` instead of ntfy. Python calls [show]. */
class Notifier(private val context: Context) {

    fun show(title: String, message: String, priority: Int): Boolean {
        if (Build.VERSION.SDK_INT >= 33 &&
            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS)
            != PackageManager.PERMISSION_GRANTED
        ) return false
        val open = PendingIntent.getActivity(
            context, 0,
            Intent(context, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_IMMUTABLE,
        )
        val urgent = priority >= 4
        val n = NotificationCompat.Builder(context, if (urgent) URGENT else ALERTS)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(title)
            .setContentText(message.lineSequence().firstOrNull { it.isNotBlank() } ?: message)
            .setStyle(NotificationCompat.BigTextStyle().bigText(message))
            .setPriority(if (urgent) NotificationCompat.PRIORITY_HIGH else NotificationCompat.PRIORITY_DEFAULT)
            .setContentIntent(open)
            .setAutoCancel(true)
            .build()
        return try {
            NotificationManagerCompat.from(context).notify(ids.incrementAndGet(), n)
            true
        } catch (e: SecurityException) {
            false
        }
    }

    companion object {
        const val ALERTS = "alertes"
        const val URGENT = "urgent"
        const val SYNC = "synchro"
        private val ids = AtomicInteger((System.currentTimeMillis() / 1000 % 100_000).toInt())

        fun createChannels(context: Context) {
            val nm = context.getSystemService(NotificationManager::class.java)
            nm.createNotificationChannels(
                listOf(
                    NotificationChannel(ALERTS, "Alertes et analyses", NotificationManager.IMPORTANCE_DEFAULT),
                    NotificationChannel(URGENT, "À confirmer (Trade Republic, CMB)", NotificationManager.IMPORTANCE_HIGH),
                    NotificationChannel(SYNC, "Synchronisation en cours", NotificationManager.IMPORTANCE_LOW),
                ),
            )
        }
    }
}
