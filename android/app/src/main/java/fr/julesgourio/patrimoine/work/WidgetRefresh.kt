package fr.julesgourio.patrimoine.work

import android.content.Context
import androidx.glance.appwidget.updateAll
import fr.julesgourio.patrimoine.engine.Engine
import fr.julesgourio.patrimoine.engine.Reply
import fr.julesgourio.patrimoine.widget.PatrimoineWidget
import fr.julesgourio.patrimoine.widget.WidgetData
import org.json.JSONArray
import org.json.JSONObject
import kotlin.math.roundToLong

/** Relit l'écran `accueil` et redessine le widget d'écran d'accueil. Sans effet si l'appel échoue. */
object WidgetRefresh {
    suspend fun run(context: Context) {
        try {
            val data = (Engine.call("accueil", Engine.args("jours" to 10)) as? Reply.Ok)?.data as? JSONObject ?: return
            val total = data.optJSONObject("patrimoine")?.takeIf { it.has("total") }?.optDouble("total") ?: return
            // Variation du jour : dernier point de `courbe` contre l'avant-dernier ([[date, valeur]]).
            val curve: JSONArray? = data.optJSONArray("courbe")
            var dayCents: Long? = null
            var fraction: Double? = null
            if (curve != null && curve.length() >= 2) {
                val last = curve.getJSONArray(curve.length() - 1).getDouble(1)
                val before = curve.getJSONArray(curve.length() - 2).getDouble(1)
                dayCents = ((last - before) * 100).roundToLong()
                if (before != 0.0) fraction = (last - before) / before
            }
            WidgetData.save(context, (total * 100).roundToLong(), dayCents, fraction, System.currentTimeMillis())
            PatrimoineWidget().updateAll(context)
        } catch (e: Exception) {
            // Le widget garde ses dernières valeurs.
        }
    }
}
