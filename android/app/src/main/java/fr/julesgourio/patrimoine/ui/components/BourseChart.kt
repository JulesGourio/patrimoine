package fr.julesgourio.patrimoine.ui.components

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.input.pointer.positionChange
import androidx.compose.ui.text.TextMeasurer
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import fr.julesgourio.patrimoine.ui.theme.Pt
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt

/** Ce que le graphique du bloc sombre dessine ; construit par l'écran Bourse à partir de la réponse du moteur. */
sealed interface ModeleBourse {
    val dates: List<String>
    /** Année affichée dans les dates de l'axe (périodes d'un an et plus). */
    val anneeAxe: Boolean

    /** Valeur en euros : aire dégradée, montant investi en pointillé si fourni. */
    class Euros(override val dates: List<String>, val valeurs: List<Double>, val investi: List<Double>?, val hausse: Boolean,
                override val anneeAxe: Boolean) : ModeleBourse

    /** Rendement en fraction : portefeuille (blanc), indice (gris), ligne de zéro. */
    class Pourcent(override val dates: List<String>, val portefeuille: List<Double>, val indice: List<Double>?,
                   override val anneeAxe: Boolean) : ModeleBourse

    /** Aires empilées, une couleur par compte. */
    class Comptes(override val dates: List<String>, val piles: List<Pair<Color, List<Double>>>, override val anneeAxe: Boolean) : ModeleBourse
}

private const val MARGE_DROITE = 8f
private val HAUT = 10.dp
private val BAS = 150.dp
private val TOTAL = 170.dp

@Composable
fun GraphiqueBourse(modele: ModeleBourse, modifier: Modifier = Modifier) {
    val n = modele.dates.size
    if (n < 2) return
    var survol by remember(modele) { mutableStateOf<Int?>(null) }
    val mesure = rememberTextMeasurer()
    val police = MaterialTheme.typography.bodySmall.fontFamily
    val axe = TextStyle(fontSize = 10.sp, color = Pt.NuitSub, fontFamily = police)
    val bulleTexte = TextStyle(fontSize = 12.sp, color = Pt.Encre, fontWeight = FontWeight.SemiBold, fontFamily = police)
    val bulleDate = TextStyle(fontSize = 12.sp, color = Pt.Sub, fontWeight = FontWeight.Medium, fontFamily = police)

    Canvas(
        modifier.fillMaxWidth().height(TOTAL).pointerInput(modele) {
            awaitEachGesture {
                val down = awaitFirstDown()
                val largeur = size.width - MARGE_DROITE.dp.toPx()
                fun indice(x: Float) = ((x / largeur).coerceIn(0f, 1f) * (n - 1)).roundToInt()
                survol = indice(down.position.x)
                do {
                    val ev = awaitPointerEvent()
                    val c = ev.changes.first()
                    survol = indice(c.position.x)
                    // Glissé horizontal : le graphique le garde ; vertical : la liste défile.
                    if (abs(c.positionChange().x) > abs(c.positionChange().y)) c.consume()
                } while (c.pressed)
                survol = null
            }
        },
    ) {
        val haut = HAUT.toPx()
        val bas = BAS.toPx()
        val l = size.width - MARGE_DROITE.dp.toPx()
        drawLine(Pt.NuitLigne, Offset(0f, haut), Offset(size.width, haut), 1.dp.toPx())
        drawLine(Pt.NuitLigne, Offset(0f, (haut + bas) / 2), Offset(size.width, (haut + bas) / 2), 1.dp.toPx())
        drawLine(Pt.NuitLigne, Offset(0f, bas), Offset(size.width, bas), 1.dp.toPx())

        fun x(i: Int) = i.toFloat() / (n - 1) * l
        val (lo, hi) = bornes(modele)
        fun y(v: Double) = (bas - ((v - lo) / (if (hi - lo == 0.0) 1.0 else hi - lo)) * (bas - haut)).toFloat()
        fun ligne(v: List<Double>): Path = Path().apply {
            v.forEachIndexed { i, a -> if (i == 0) moveTo(x(i), y(a)) else lineTo(x(i), y(a)) }
        }

        var pointSurvol: Offset? = null
        var texteSurvol = ""
        when (modele) {
            is ModeleBourse.Euros -> {
                val c = if (modele.hausse) Pt.HausseNuit else Pt.BaisseNuit
                val p = ligne(modele.valeurs)
                val aire = Path().apply { addPath(p); lineTo(l, bas); lineTo(0f, bas); close() }
                drawPath(aire, Brush.verticalGradient(listOf(c.copy(alpha = 0.28f), c.copy(alpha = 0f)), startY = haut, endY = bas))
                modele.investi?.let {
                    drawPath(ligne(it), Pt.NuitSub, style = Stroke(1.4.dp.toPx(), pathEffect = PathEffect.dashPathEffect(floatArrayOf(3.dp.toPx(), 4.dp.toPx()))))
                }
                drawPath(p, c, style = Stroke(2.dp.toPx(), join = StrokeJoin.Round, cap = StrokeCap.Round))
                val fin = Offset(l, y(modele.valeurs.last()))
                drawCircle(Pt.Nuit, 6.dp.toPx(), fin)
                drawCircle(c, 4.dp.toPx(), fin)
                survol?.let { pointSurvol = Offset(x(it), y(modele.valeurs[it])); texteSurvol = euros(modele.valeurs[it], cents = false) }
            }
            is ModeleBourse.Pourcent -> {
                val zy = y(0.0)
                drawLine(Color(0xFF3A445C), Offset(0f, zy), Offset(size.width, zy), 1.dp.toPx(),
                    pathEffect = PathEffect.dashPathEffect(floatArrayOf(2.dp.toPx(), 3.dp.toPx())))
                modele.indice?.let { drawPath(ligne(it), Pt.NuitSub, style = Stroke(1.6.dp.toPx(), join = StrokeJoin.Round)) }
                drawPath(ligne(modele.portefeuille), Color.White, style = Stroke(2.dp.toPx(), join = StrokeJoin.Round, cap = StrokeCap.Round))
                survol?.let { pointSurvol = Offset(x(it), y(modele.portefeuille[it])); texteSurvol = pct(modele.portefeuille[it], digits = 2) }
            }
            is ModeleBourse.Comptes -> {
                val cumul = DoubleArray(n)
                modele.piles.forEach { (couleur, v) ->
                    val avant = cumul.copyOf()
                    for (i in 0 until n) cumul[i] += v.getOrElse(i) { 0.0 }
                    val aire = Path().apply {
                        for (i in 0 until n) if (i == 0) moveTo(x(i), y(cumul[i])) else lineTo(x(i), y(cumul[i]))
                        for (i in n - 1 downTo 0) lineTo(x(i), y(avant[i]))
                        close()
                    }
                    drawPath(aire, couleur)
                    drawPath(aire, Pt.Nuit, style = Stroke(1.5.dp.toPx()))
                }
                survol?.let { pointSurvol = Offset(x(it), y(cumul[it])); texteSurvol = euros(cumul[it], cents = false) }
            }
        }

        // Axes : bornes à gauche, première et dernière dates en pied.
        val fmt: (Double) -> String = if (modele is ModeleBourse.Pourcent) { v -> pct(v, digits = 1) } else { v -> eurosK(v) }
        drawText(mesure, fmt(hi), Offset(6.dp.toPx(), haut + 1.dp.toPx()), axe)
        drawText(mesure, fmt(lo), Offset(6.dp.toPx(), bas - 14.dp.toPx()), axe)
        val pied = 170.dp.toPx() - 15.dp.toPx()
        drawText(mesure, dateCourte(modele.dates.first(), modele.anneeAxe), Offset(6.dp.toPx(), pied), axe)
        val fin = mesure.measure(dateCourte(modele.dates.last(), modele.anneeAxe), axe)
        drawText(mesure, dateCourte(modele.dates.last(), modele.anneeAxe), Offset(size.width - 6.dp.toPx() - fin.size.width, pied), axe)

        pointSurvol?.let { p ->
            drawLine(Color.White.copy(alpha = 0.5f), Offset(p.x, haut), Offset(p.x, bas), 1.dp.toPx())
            drawCircle(Pt.Nuit, 6.5.dp.toPx(), p)
            drawCircle(Color.White, 4.5.dp.toPx(), p)
            bulle(mesure, texteSurvol, dateCourte(modele.dates[survol!!], true), p.x, bulleTexte, bulleDate)
        }
    }
}

private fun bornes(m: ModeleBourse): Pair<Double, Double> = when (m) {
    is ModeleBourse.Euros -> {
        val tous = m.valeurs + (m.investi ?: emptyList())
        val lo = tous.min()
        val hi = tous.max()
        val pv = (hi - lo) * 0.1
        max(0.0, lo - (if (pv == 0.0) 1.0 else pv)) to hi + (if (pv == 0.0) 1.0 else pv)
    }
    is ModeleBourse.Pourcent -> {
        val tous = m.portefeuille + (m.indice ?: emptyList())
        val lo = tous.min()
        val hi = tous.max()
        val pv = (hi - lo) * 0.1
        val p = if (pv == 0.0) 0.001 else pv
        (min(lo, 0.0) - p) to (max(hi, 0.0) + p)
    }
    is ModeleBourse.Comptes -> {
        val n = m.dates.size
        val maxTotal = (0 until n).maxOf { i -> m.piles.sumOf { it.second.getOrElse(i) { 0.0 } } }
        0.0 to (if (maxTotal <= 0) 1.0 else maxTotal * 1.08)
    }
}

private fun DrawScope.bulle(mesure: TextMeasurer, valeur: String, date: String, xCentre: Float, sv: TextStyle, sd: TextStyle) {
    val a = mesure.measure(valeur, sv)
    val b = mesure.measure(date, sd)
    val pad = 8.dp.toPx()
    val ecart = 6.dp.toPx()
    val w = a.size.width + ecart + b.size.width + 2 * pad
    val h = max(a.size.height, b.size.height) + 10.dp.toPx()
    val x0 = (xCentre - w / 2).coerceIn(0f, size.width - w)
    drawRoundRect(Color.White, Offset(x0, 0f), Size(w, h), CornerRadius(8.dp.toPx()))
    drawText(mesure, valeur, Offset(x0 + pad, 5.dp.toPx()), sv)
    drawText(mesure, date, Offset(x0 + pad + a.size.width + ecart, 5.dp.toPx()), sd)
}
