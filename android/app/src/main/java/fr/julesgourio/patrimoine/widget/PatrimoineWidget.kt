package fr.julesgourio.patrimoine.widget

import android.content.Context
import android.content.Intent
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.glance.GlanceId
import androidx.glance.GlanceModifier
import androidx.glance.appwidget.action.actionStartActivity
import androidx.glance.action.clickable
import androidx.glance.appwidget.GlanceAppWidget
import androidx.glance.appwidget.GlanceAppWidgetReceiver
import androidx.glance.appwidget.provideContent
import androidx.glance.appwidget.cornerRadius
import androidx.glance.background
import androidx.glance.layout.Alignment
import androidx.glance.layout.Column
import androidx.glance.layout.fillMaxSize
import androidx.glance.layout.padding
import androidx.glance.text.FontWeight
import androidx.glance.text.Text
import androidx.glance.text.TextStyle
import androidx.glance.unit.ColorProvider
import androidx.compose.ui.graphics.Color
import fr.julesgourio.patrimoine.ui.MainActivity
import fr.julesgourio.patrimoine.ui.components.euros
import fr.julesgourio.patrimoine.ui.components.pct
import java.time.format.DateTimeFormatter

/** Dernières valeurs affichées, écrites par [WidgetRefresh] (centimes entiers : jamais d'appel Python ici). */
internal object WidgetData {
    private const val PREFS = "widget_patrimoine"

    fun save(context: Context, totalCents: Long, dayCents: Long?, dayFraction: Double?, updatedAt: Long) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().apply {
            putLong("total", totalCents)
            if (dayCents != null) putLong("jour", dayCents) else remove("jour")
            if (dayFraction != null) putFloat("jour_pct", dayFraction.toFloat()) else remove("jour_pct")
            putLong("maj", updatedAt)
        }.apply()
    }

    fun read(context: Context): Snapshot? {
        val p = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        if (!p.contains("total")) return null
        return Snapshot(
            total = p.getLong("total", 0) / 100.0,
            day = if (p.contains("jour")) p.getLong("jour", 0) / 100.0 else null,
            dayFraction = if (p.contains("jour_pct")) p.getFloat("jour_pct", 0f).toDouble() else null,
            updatedAt = p.getLong("maj", 0),
        )
    }

    class Snapshot(val total: Double, val day: Double?, val dayFraction: Double?, val updatedAt: Long)
}

class PatrimoineWidget : GlanceAppWidget() {
    override suspend fun provideGlance(context: Context, id: GlanceId) {
        val data = WidgetData.read(context)
        provideContent {
            val open = actionStartActivity(Intent(context, MainActivity::class.java))
            Column(
                modifier = GlanceModifier.fillMaxSize().background(Color(0xFF1B1F27)).cornerRadius(20.dp)
                    .padding(12.dp).clickable(open),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                if (data == null) {
                    Text("Patrimoine", style = TextStyle(color = ColorProvider(Color.White), fontSize = 14.sp))
                    Text("Ouvrir l'appli pour synchroniser",
                        style = TextStyle(color = ColorProvider(Color(0xFFB0B6C0)), fontSize = 12.sp))
                } else {
                    val tone = when {
                        (data.day ?: 0.0) > 0 -> Color(0xFF4CD08A)
                        (data.day ?: 0.0) < 0 -> Color(0xFFFF6B6B)
                        else -> Color(0xFFB0B6C0)
                    }
                    Text(euros(data.total, cents = false),
                        style = TextStyle(color = ColorProvider(Color.White), fontSize = 26.sp, fontWeight = FontWeight.Bold))
                    Text(
                        if (data.day == null) "Écart depuis la veille : —"
                        else "${euros(data.day, sign = true)} (${pct(data.dayFraction)}) depuis la veille (flux inclus)",
                        style = TextStyle(color = ColorProvider(tone), fontSize = 14.sp),
                    )
                    val time = java.time.Instant.ofEpochMilli(data.updatedAt).atZone(java.time.ZoneId.systemDefault())
                        .toLocalTime().format(DateTimeFormatter.ofPattern("HH:mm"))
                    Text("Mis à jour à $time",
                        style = TextStyle(color = ColorProvider(Color(0xFFB0B6C0)), fontSize = 11.sp))
                }
            }
        }
    }
}

class PatrimoineWidgetReceiver : GlanceAppWidgetReceiver() {
    override val glanceAppWidget: GlanceAppWidget = PatrimoineWidget()
}
