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
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.input.pointer.positionChange
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

/**
 * Un mois du graphique des flux : revenus empilés par source (au-dessus de la ligne), dépenses (en dessous) et épargne.
 * [detail] : lignes de l'infobulle quand on touche le mois (titre, revenus par source, dépenses, épargne, taux).
 */
data class BarreFlux(val lettre: String, val sources: List<Pair<Color, Double>>, val depenses: Double, val epargne: Double,
                     val detail: List<LigneInfobulle> = emptyList())

val CouleurDepenses = Color(0xFFFF8D83)

private val HAUT_FLUX = 190.dp
private val LIGNE_FLUX = 118.dp

/**
 * Graphique du bloc sombre de l'écran Flux (maquette) : un mois par colonne, revenus empilés au-dessus de la ligne de
 * base, dépenses en dessous, épargne nette en courbe blanche. [choix] est le mois mis en avant ; toucher ou glisser
 * le change et affiche l'infobulle détaillée du mois touché.
 */
@Composable
fun GraphiqueFlux(barres: List<BarreFlux>, choix: Int, onChoix: (Int) -> Unit, modifier: Modifier = Modifier) {
    val n = barres.size
    if (n == 0) return
    val mesure = rememberTextMeasurer()
    val police = MaterialTheme.typography.bodySmall.fontFamily
    // Pas de clé : toucher change le mois (donc `barres`), l'état ne doit pas être réinitialisé pendant le geste.
    var survol by remember { mutableStateOf<Int?>(null) }
    val choisir by rememberUpdatedState(onChoix)
    Canvas(
        modifier.fillMaxWidth().height(HAUT_FLUX).pointerInput(n) {
            awaitEachGesture {
                val down = awaitFirstDown()
                fun indice(x: Float) = ((x / size.width) * n).toInt().coerceIn(0, n - 1)
                survol = indice(down.position.x).also { choisir(it) }
                do {
                    val ev = awaitPointerEvent()
                    val c = ev.changes.first()
                    val i = indice(c.position.x)
                    if (i != survol) { survol = i; choisir(i) }
                    // Glissé horizontal : le graphique le garde ; vertical : la liste défile.
                    if (abs(c.positionChange().x) > abs(c.positionChange().y)) c.consume()
                } while (c.pressed)
                survol = null
            }
        },
    ) {
        val z = LIGNE_FLUX.toPx()
        val haut = 12.dp.toPx()
        val sous = size.height - z - 24.dp.toPx()   // place sous la ligne pour les dépenses (étiquettes en pied)
        val plafond = max(barres.maxOf { b -> b.sources.sumOf { it.second } }, 1.0)
        val k = ((z - haut) / plafond).toFloat()
        val pas = size.width / n
        val l = min(pas * 0.62f, 22.dp.toPx())
        drawLine(Pt.NuitLigne, Offset(0f, z), Offset(size.width, z), 1.dp.toPx())
        val net = ArrayList<Offset>(n)
        barres.forEachIndexed { i, b ->
            val x = i * pas + (pas - l) / 2
            val alpha = if (i == choix) 1f else 0.72f
            var y = z
            b.sources.forEach { (c, v) ->
                val h = (v * k).toFloat()
                if (h <= 0f) return@forEach
                y -= h
                drawRoundRect(c.copy(alpha = alpha), Offset(x, y), Size(l, max(h - 1.5.dp.toPx(), 1f)), CornerRadius(2.5.dp.toPx()))
            }
            val dh = min((max(b.depenses, 0.0) * k).toFloat(), sous)
            if (dh > 0f) drawRoundRect(CouleurDepenses.copy(alpha = alpha), Offset(x, z + 1.5.dp.toPx()), Size(l, dh), CornerRadius(2.5.dp.toPx()))
            net += Offset(x + l / 2, (z - b.epargne * k).toFloat().coerceIn(haut - 4.dp.toPx(), z + sous))
            val style = TextStyle(fontSize = 10.sp, fontFamily = police, color = if (i == choix) Color.White else Pt.NuitSub,
                fontWeight = if (i == choix) FontWeight.SemiBold else FontWeight.Normal)
            val m = mesure.measure(b.lettre, style)
            drawText(mesure, b.lettre, Offset(x + l / 2 - m.size.width / 2f, size.height - m.size.height - 1.dp.toPx()), style)
        }
        val chemin = Path().apply { net.forEachIndexed { i, p -> if (i == 0) moveTo(p.x, p.y) else lineTo(p.x, p.y) } }
        drawPath(chemin, Color.White, style = Stroke(1.6.dp.toPx(), join = StrokeJoin.Round, cap = StrokeCap.Round))
        net.forEach { p ->
            drawCircle(Pt.Nuit, 3.8.dp.toPx(), p)
            drawCircle(Color.White, 2.6.dp.toPx(), p)
        }
        survol?.let { i ->
            val b = barres[i]
            if (b.detail.isNotEmpty()) infobulleDetaillee(mesure, b.detail, i * pas + pas / 2, 0f, InfobulleClaire)
        }
    }
}

/**
 * Courbe du taux d'épargne (fractions), sur fond clair ; les mois sans valeur (null) sont sautés. Bornes arrondies à
 * 10 points, étiquettes de bornes et du dernier mois comme dans la maquette. Toucher ou glisser donne le détail du
 * mois ([detail] : lignes de l'infobulle du mois d'indice donné).
 */
@Composable
fun CourbeTaux(valeurs: List<Double?>, dernierMois: String, modifier: Modifier = Modifier, detail: (Int) -> List<LigneInfobulle> = { emptyList() }) {
    val pts = valeurs.mapIndexedNotNull { i, v -> if (v == null) null else i to v }
    if (pts.size < 2) return
    val mesure = rememberTextMeasurer()
    val police = MaterialTheme.typography.bodySmall.fontFamily
    val style = TextStyle(fontSize = 10.sp, fontFamily = police, color = Pt.Mute)
    var survol by remember { mutableStateOf<Int?>(null) }
    val nb = valeurs.size
    Canvas(
        modifier.fillMaxWidth().height(86.dp).pointerInput(valeurs) {
            awaitEachGesture {
                val down = awaitFirstDown()
                val marge = 8.dp.toPx()
                fun proche(x: Float): Int {
                    val brut = ((x - marge) / (size.width - 2 * marge) * max(nb - 1, 1)).let { Math.round(it) }
                    return pts.minBy { abs(it.first - brut) }.first
                }
                survol = proche(down.position.x)
                do {
                    val ev = awaitPointerEvent()
                    val c = ev.changes.first()
                    survol = proche(c.position.x)
                    if (abs(c.positionChange().x) > abs(c.positionChange().y)) c.consume()
                } while (c.pressed)
                survol = null
            }
        },
    ) {
        val lo = kotlin.math.floor(pts.minOf { it.second } * 10) / 10
        val hi = kotlin.math.ceil(pts.maxOf { it.second } * 10) / 10
        val etendue = if (hi - lo < 0.1) 0.1 else hi - lo
        val haut = 15.dp.toPx()   // laisse la place de l'étiquette de borne au-dessus de la grille
        val bas = 70.dp.toPx()
        fun y(v: Double) = (bas - ((v - lo) / etendue).toFloat() * (bas - haut))
        listOf(haut, (haut + bas) / 2, bas).forEach { drawLine(Pt.Ligne, Offset(0f, it), Offset(size.width, it), 1.dp.toPx()) }
        val marge = 8.dp.toPx()
        fun x(i: Int) = marge + i * (size.width - 2 * marge) / max(valeurs.size - 1, 1)
        val chemin = Path().apply { pts.forEachIndexed { j, (i, v) -> if (j == 0) moveTo(x(i), y(v)) else lineTo(x(i), y(v)) } }
        drawPath(chemin, Pt.Hausse, style = Stroke(2.dp.toPx(), join = StrokeJoin.Round, cap = StrokeCap.Round))
        val (i, v) = pts.last()
        drawCircle(Color.White, 5.dp.toPx(), Offset(x(i), y(v)))
        drawCircle(Pt.Hausse, 3.5.dp.toPx(), Offset(x(i), y(v)))
        val haute = pct(hi, sign = false, digits = 0)
        drawText(mesure, haute, Offset(size.width - mesure.measure(haute, style).size.width, 0f), style)
        drawText(mesure, pct(lo, sign = false, digits = 0), Offset(0f, 72.dp.toPx()), style)
        drawText(mesure, dernierMois, Offset(size.width - mesure.measure(dernierMois, style).size.width, 72.dp.toPx()), style)
        survol?.let { k ->
            val p = Offset(x(k), y(valeurs[k] ?: return@let))
            drawLine(Pt.Mute.copy(alpha = 0.5f), Offset(p.x, haut), Offset(p.x, bas), 1.dp.toPx())
            drawCircle(Color.White, 6.dp.toPx(), p)
            drawCircle(Pt.Hausse, 4.dp.toPx(), p)
            infobulleDetaillee(mesure, detail(k), p.x, 0f, InfobulleSombre)
        }
    }
}
