package fr.julesgourio.patrimoine.ui.components

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectHorizontalDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.RoundRect
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import java.time.LocalDate
import kotlin.math.abs
import kotlin.math.atan2
import kotlin.math.ceil
import kotlin.math.floor
import kotlin.math.hypot
import kotlin.math.log10
import kotlin.math.max
import kotlin.math.min
import kotlin.math.pow
import kotlin.math.roundToInt
import kotlin.math.roundToLong

/**
 * Une courbe : points = (date ISO yyyy-MM-dd, valeur), triés.
 * [fillArea] : null = auto (remplie si c'est la seule série non pointillée) ; [width] : épaisseur du trait.
 */
data class ChartSeries(
    val name: String,
    val points: List<Pair<String, Double>>,
    val color: Color? = null,
    val dashed: Boolean = false,
    val fillArea: Boolean? = null,
    val width: Dp = 2.2.dp,
)

/** Une barre empilée : parts = (catégorie, montant >= 0). */
data class BarGroup(val label: String, val parts: List<Pair<String, Double>>, val key: String? = null)

/** Une part d'anneau ou une ligne de barres horizontales. */
data class Slice(val label: String, val value: Double, val key: String? = null, val color: Color? = null)

/** Un repère sur une [RangeBar] (cours, prix de revient, objectif…). */
class RangeMarker(val label: String, val value: Double, val color: Color)

private val BASE_PALETTE = listOf(
    Color(0xFF4C8DFF), Color(0xFF2ECC8F), Color(0xFFFFB020), Color(0xFFB57BFF),
    Color(0xFFE87BA4), Color(0xFF2FC4D9), Color(0xFF9AD04B), Color(0xFF8B93A3),
)

/** Palette catégorielle stable (mêmes couleurs dans le même ordre) ; le rouge est réservé aux pertes et dépassements. */
fun chartPalette(n: Int): List<Color> = List(max(n, 0)) { i ->
    if (i < BASE_PALETTE.size) BASE_PALETTE[i] else Color.hsv(((i * 47) % 360).toFloat(), 0.5f, 0.78f)
}

private val ACTIVE_BLUE = Color(0xFF4C8DFF)
private val TIP_BG = Color(0xFF0B0C10)
private val TIP_BORDER = Color(0xFF2A2F3A)
private val TIP_TEXT = Color(0xFFE8EAEE)

private val MONTHS = listOf("janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc.")

private fun parseDate(s: String): LocalDate? = try {
    LocalDate.parse(s.take(10))
} catch (e: Exception) {
    null
}

/** « 09 janv. 26 ». */
private fun chartDate(s: String): String {
    val d = parseDate(s) ?: return s
    return d.dayOfMonth.toString().padStart(2, '0') + " " + MONTHS[d.monthValue - 1] + " " +
        (d.year % 100).toString().padStart(2, '0')
}

private fun niceStep(range: Double, target: Int): Double {
    val raw = range / max(target, 1)
    if (raw.isNaN() || raw <= 0.0) return 1.0
    val mag = 10.0.pow(floor(log10(raw)))
    val f = raw / mag
    val nice = when {
        f <= 1.0 -> 1.0
        f <= 2.0 -> 2.0
        f <= 2.5 -> 2.5
        f <= 5.0 -> 5.0
        else -> 10.0
    }
    return nice * mag
}

/** Repères « ronds » entre lo et hi (3 à 6 en général). */
private fun niceTicks(lo: Double, hi: Double, target: Int = 4): List<Double> {
    val step = niceStep(hi - lo, target)
    val first = ceil(lo / step - 1e-9)
    val out = ArrayList<Double>()
    var k = 0
    while (k < 12) {
        val v = (first + k) * step
        if (v > hi + step * 1e-9) break
        out.add(v)
        k++
    }
    return out
}

private fun trimNum(x: Double): String {
    val r = (x * 10).roundToLong() / 10.0
    return if (r == r.toLong().toDouble()) r.toLong().toString() else r.toString().replace('.', ',')
}

private fun compactEuros(v: Double): String {
    val a = abs(v)
    return when {
        a >= 1_000_000 -> trimNum(v / 1_000_000) + " M€"
        a >= 1_000 -> trimNum(v / 1_000) + " k€"
        else -> trimNum(v) + " €"
    }
}

/** Libellés d'axe : compacts (« 45 k€ ») quand les valeurs sont des euros, sinon [valueFormat]. */
private fun axisFormatter(valueFormat: (Double) -> String, axisFormat: ((Double) -> String)?): (Double) -> String {
    if (axisFormat != null) return axisFormat
    if (!valueFormat(45000.0).contains('€')) return valueFormat
    val compact: (Double) -> String = { v -> compactEuros(v) }
    return compact
}

/** Séries alignées sur l'union des dates, avec report de la dernière valeur connue (null avant la première). */
private class Aligned(val dates: List<String>, val values: List<List<Double?>>)

private fun alignSeries(series: List<ChartSeries>): Aligned {
    val dates = series.flatMap { s -> s.points.map { it.first.take(10) } }.toSortedSet().toList()
    val values = series.map { s ->
        val byDate = HashMap<String, Double>()
        s.points.forEach { byDate[it.first.take(10)] = it.second }
        var last: Double? = null
        dates.map { d ->
            byDate[d]?.let { last = it }
            last
        }
    }
    return Aligned(dates, values)
}

private val PERIODS = listOf("1 M" to 30L, "6 M" to 182L, "1 A" to 365L, "5 A" to 1825L, "Tout" to null)

/** Puce de période : fond sombre, active en bleu. */
@Composable
private fun Pill(text: String, selected: Boolean, onClick: () -> Unit) {
    val scheme = MaterialTheme.colorScheme
    val shape = RoundedCornerShape(50)
    Box(
        Modifier
            .clip(shape)
            .background(if (selected) ACTIVE_BLUE else scheme.surfaceContainerHigh)
            .clickable(onClick = onClick)
            .padding(horizontal = 14.dp, vertical = 6.dp),
        contentAlignment = Alignment.Center,
    ) {
        Text(
            text,
            style = MaterialTheme.typography.labelMedium,
            color = if (selected) Color.White else scheme.onSurfaceVariant,
            fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Normal,
            maxLines = 1,
        )
    }
}

/** Entrée de légende : pastille ronde + nom ; estompée si masquée. */
@Composable
private fun LegendItem(text: String, color: Color, dimmed: Boolean = false, onClick: (() -> Unit)? = null) {
    val scheme = MaterialTheme.colorScheme
    Row(
        Modifier
            .clip(RoundedCornerShape(50))
            .let { if (onClick != null) it.clickable(onClick = onClick) else it }
            .padding(horizontal = 4.dp, vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(Modifier.size(9.dp).clip(CircleShape).background(if (dimmed) color.copy(alpha = 0.3f) else color))
        Spacer(Modifier.width(6.dp))
        Text(
            text,
            style = MaterialTheme.typography.labelMedium,
            color = if (dimmed) scheme.onSurfaceVariant.copy(alpha = 0.5f) else scheme.onSurfaceVariant,
            maxLines = 1,
        )
    }
}

@Composable
private fun Dot(color: Color) {
    Box(Modifier.size(8.dp).clip(CircleShape).background(color))
}

/** Bulle sombre arrondie (infobulle des barres). */
@Composable
private fun ChartBubble(content: @Composable () -> Unit) {
    Surface(
        modifier = Modifier.border(1.dp, TIP_BORDER, RoundedCornerShape(10.dp)),
        shape = RoundedCornerShape(10.dp),
        color = TIP_BG,
        contentColor = TIP_TEXT,
        shadowElevation = 2.dp,
        content = content,
    )
}

@Composable
fun InteractiveLineChart(
    series: List<ChartSeries>,
    modifier: Modifier = Modifier,
    height: Dp = 200.dp,
    showPeriods: Boolean = true,
    stacked: Boolean = false,
    showChange: Boolean = true,
    valueFormat: (Double) -> String = { euros(it) },
    axisFormat: ((Double) -> String)? = null,
) {
    if (series.isEmpty() || series.all { it.points.size < 2 }) {
        Muted("Pas encore assez d'historique pour une courbe.")
        return
    }
    val scheme = MaterialTheme.colorScheme
    val palette = chartPalette(series.size)
    val colors = series.mapIndexed { i, s -> s.color ?: palette[i] }
    val aligned = remember(series) { alignSeries(series) }

    var hidden by remember(series) { mutableStateOf(setOf<Int>()) }
    var periodSel by remember(series) { mutableStateOf<String?>(null) }
    var selRaw by remember(series) { mutableStateOf<Int?>(null) }

    val lastDate = aligned.dates.lastOrNull()?.let { parseDate(it) }
    val firstDate = aligned.dates.firstOrNull()?.let { parseDate(it) }
    val defaultPeriod = if (lastDate != null && firstDate != null && firstDate.isBefore(lastDate.minusDays(365))) "1 A" else "Tout"
    val period = if (showPeriods) (periodSel ?: defaultPeriod) else "Tout"
    val days = PERIODS.firstOrNull { it.first == period }?.second
    var startIdx = 0
    if (days != null && lastDate != null) {
        val cutoff = lastDate.minusDays(days)
        val found = aligned.dates.indexOfFirst { d -> parseDate(d)?.let { !it.isBefore(cutoff) } ?: false }
        if (found >= 0) startIdx = found
    }
    val dates = aligned.dates.subList(startIdx, aligned.dates.size)
    val n = dates.size
    val vals = aligned.values.map { it.subList(startIdx, it.size) }
    val visible = series.indices.filter { it !in hidden }

    // Valeurs tracées : cumul si empilé.
    val plotted: List<List<Double?>> = if (stacked) {
        val run = DoubleArray(n)
        series.indices.map { s ->
            if (s in hidden) List<Double?>(n) { null } else List<Double?>(n) { i ->
                run[i] += vals[s][i] ?: 0.0
                run[i]
            }
        }
    } else vals
    val lo: Double
    val hi: Double
    if (stacked) {
        lo = 0.0
        hi = visible.maxOfOrNull { s -> plotted[s].maxOfOrNull { it ?: 0.0 } ?: 0.0 } ?: 1.0
    } else {
        val all = visible.flatMap { s -> plotted[s].filterNotNull() }
        lo = all.minOrNull() ?: 0.0
        hi = all.maxOrNull() ?: 1.0
    }
    val span = if (hi - lo > 0) hi - lo else 1.0
    val sel = selRaw?.takeIf { it in 0 until n }

    val firstVisible = visible.firstOrNull()
    val refSeries = if (0 in visible) 0 else firstVisible
    val refValues = if (stacked) {
        (0 until n).mapNotNull { i -> visible.mapNotNull { vals[it].getOrNull(i) }.takeIf { l -> l.isNotEmpty() }?.sum() }
    } else {
        refSeries?.let { vals[it].filterNotNull() }.orEmpty()
    }
    val startV = refValues.firstOrNull()
    val endV = refValues.lastOrNull()

    val gridColor = scheme.outlineVariant
    val ringColor = scheme.surface
    val axisStyle = TextStyle(fontSize = 10.sp, color = scheme.onSurfaceVariant)
    val tipStyle = TextStyle(fontSize = 11.sp, color = TIP_TEXT)
    val tipBold = TextStyle(fontSize = 11.sp, color = TIP_TEXT, fontWeight = FontWeight.SemiBold)
    val measurer = rememberTextMeasurer()
    val density = LocalDensity.current
    val fmtAxis = axisFormatter(valueFormat, axisFormat)
    val yTicks = niceTicks(lo, hi, 4)
    val yLabels = yTicks.map { fmtAxis(it) }
    val labelW = yLabels.maxOfOrNull { measurer.measure(it, axisStyle).size.width } ?: 0
    val leftPx = labelW + with(density) { 10.dp.toPx() }
    val rightPx = with(density) { 6.dp.toPx() }
    val autoFill = series.count { !it.dashed } == 1

    val summary = buildString {
        append("Graphique de ")
        append(series.joinToString(", ") { it.name })
        append(", du ${day(dates.firstOrNull())} au ${day(dates.lastOrNull())}.")
        if (startV != null && endV != null) append(" De ${valueFormat(startV)} à ${valueFormat(endV)}.")
    }

    Column(modifier.fillMaxWidth().semantics { contentDescription = summary }, verticalArrangement = Arrangement.spacedBy(8.dp)) {
        if (showPeriods) {
            Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                PERIODS.forEach { (label, _) ->
                    Pill(label, selected = label == period) {
                        periodSel = label
                        selRaw = null
                    }
                }
            }
        }
        if (n < 2) {
            Muted("Pas assez de points sur cette période.")
        } else {
            Canvas(
                Modifier
                    .fillMaxWidth()
                    .height(height)
                    .pointerInput(n, leftPx) {
                        detectTapGestures { off ->
                            val pw = max(size.width - leftPx - rightPx, 1f)
                            selRaw = (((off.x - leftPx) / pw) * (n - 1)).roundToInt().coerceIn(0, n - 1)
                        }
                    }
                    .pointerInput(n, leftPx) {
                        detectHorizontalDragGestures(
                            onDragStart = { off ->
                                val pw = max(size.width - leftPx - rightPx, 1f)
                                selRaw = (((off.x - leftPx) / pw) * (n - 1)).roundToInt().coerceIn(0, n - 1)
                            },
                        ) { change, _ ->
                            val pw = max(size.width - leftPx - rightPx, 1f)
                            selRaw = (((change.position.x - leftPx) / pw) * (n - 1)).roundToInt().coerceIn(0, n - 1)
                            change.consume()
                        }
                    },
            ) {
                val w = size.width
                val top = 8.dp.toPx()
                val bottom = size.height - 20.dp.toPx()
                val plotH = bottom - top
                val plotW = w - leftPx - rightPx
                fun px(i: Int) = leftPx + plotW * i / (n - 1)
                fun py(v: Double) = (bottom - plotH * (v - lo) / span).toFloat()

                // Grille très discrète et repères de l'axe Y.
                yTicks.forEachIndexed { k, t ->
                    val yy = py(t)
                    drawLine(gridColor.copy(alpha = 0.35f), Offset(leftPx, yy), Offset(w - rightPx, yy), strokeWidth = 1.dp.toPx())
                    val lay = measurer.measure(yLabels[k], axisStyle)
                    drawText(lay, topLeft = Offset(leftPx - 6.dp.toPx() - lay.size.width, yy - lay.size.height / 2f))
                }
                // Repères de l'axe X (4 dates).
                val xCount = min(4, n)
                for (k in 0 until xCount) {
                    val i = if (xCount == 1) 0 else (k * (n - 1).toFloat() / (xCount - 1)).roundToInt()
                    val lay = measurer.measure(chartDate(dates[i]), axisStyle)
                    val x = (px(i) - lay.size.width / 2f).coerceIn(0f, max(0f, w - lay.size.width))
                    drawText(lay, topLeft = Offset(x, bottom + 5.dp.toPx()))
                }

                fun linePath(values: List<Double?>): Path {
                    val p = Path()
                    var pen = false
                    for (i in 0 until n) {
                        val v = values[i]
                        if (v == null) {
                            pen = false
                        } else if (!pen) {
                            p.moveTo(px(i), py(v))
                            pen = true
                        } else {
                            p.lineTo(px(i), py(v))
                        }
                    }
                    return p
                }
                if (stacked) {
                    var prev: List<Double?> = List(n) { 0.0 }
                    for (s in visible) {
                        val topV = plotted[s]
                        val area = Path()
                        area.moveTo(px(0), py(topV[0] ?: 0.0))
                        for (i in 1 until n) area.lineTo(px(i), py(topV[i] ?: 0.0))
                        for (i in n - 1 downTo 0) area.lineTo(px(i), py(prev[i] ?: 0.0))
                        area.close()
                        drawPath(area, colors[s].copy(alpha = 0.7f))
                        prev = topV
                    }
                    for (s in visible) {
                        drawPath(
                            linePath(plotted[s]), colors[s],
                            style = Stroke(1.dp.toPx(), cap = StrokeCap.Round, join = StrokeJoin.Round),
                        )
                    }
                } else {
                    for (s in visible) {
                        if (!(series[s].fillArea ?: autoFill)) continue
                        val first = plotted[s].indexOfFirst { it != null }
                        val lastI = plotted[s].indexOfLast { it != null }
                        if (first in 0 until lastI) {
                            val fill = Path().apply {
                                addPath(linePath(plotted[s]))
                                lineTo(px(lastI), bottom)
                                lineTo(px(first), bottom)
                                close()
                            }
                            drawPath(
                                fill,
                                Brush.verticalGradient(
                                    listOf(colors[s].copy(alpha = 0.2f), colors[s].copy(alpha = 0f)),
                                    startY = top, endY = bottom,
                                ),
                            )
                        }
                    }
                    for (s in visible) {
                        val effect = if (series[s].dashed) PathEffect.dashPathEffect(floatArrayOf(14f, 10f)) else null
                        drawPath(
                            linePath(plotted[s]), colors[s],
                            style = Stroke(series[s].width.toPx(), cap = StrokeCap.Round, join = StrokeJoin.Round, pathEffect = effect),
                        )
                    }
                }

                if (sel != null) {
                    val cx = px(sel)
                    drawLine(
                        Color(0xFF8B93A3), Offset(cx, top), Offset(cx, bottom), strokeWidth = 1.dp.toPx(),
                        pathEffect = PathEffect.dashPathEffect(floatArrayOf(8f, 8f)),
                    )
                    for (s in visible) {
                        val v = plotted[s][sel] ?: continue
                        drawCircle(ringColor, 5.5.dp.toPx(), Offset(cx, py(v)))
                        drawCircle(colors[s], 3.8.dp.toPx(), Offset(cx, py(v)))
                    }

                    // Bulle sombre : date, une ligne par série, total si empilé.
                    val rows = ArrayList<Triple<Color?, String, Boolean>>()
                    rows.add(Triple(null, chartDate(dates[sel]), true))
                    var total = 0.0
                    for (s in visible) {
                        val v = vals[s][sel]
                        if (v != null) total += v
                        val txt = (if (series.size > 1) series[s].name + " : " else "") + (v?.let(valueFormat) ?: "—")
                        rows.add(Triple(colors[s], txt, false))
                    }
                    if (stacked && visible.size > 1) rows.add(Triple(null, "Total : " + valueFormat(total), true))
                    val lays = rows.map { measurer.measure(it.second, if (it.third) tipBold else tipStyle) }
                    val pad = 8.dp.toPx()
                    val dotSpace = 14.dp.toPx()
                    val gap = 3.dp.toPx()
                    val textW = lays.mapIndexed { i, l -> l.size.width.toFloat() + (if (rows[i].first != null) dotSpace else 0f) }.max()
                    val boxW = textW + 2 * pad
                    val boxH = lays.sumOf { it.size.height.toDouble() }.toFloat() + gap * (lays.size - 1) + 2 * pad
                    var bx = cx + 12.dp.toPx()
                    if (bx + boxW > w) bx = cx - 12.dp.toPx() - boxW
                    bx = bx.coerceIn(0f, max(0f, w - boxW))
                    val by = top
                    val corner = CornerRadius(10.dp.toPx())
                    drawRoundRect(TIP_BG, Offset(bx, by), Size(boxW, boxH), corner)
                    drawRoundRect(TIP_BORDER, Offset(bx, by), Size(boxW, boxH), corner, style = Stroke(1.dp.toPx()))
                    var yy = by + pad
                    lays.forEachIndexed { i, l ->
                        val c = rows[i].first
                        var tx = bx + pad
                        if (c != null) {
                            drawCircle(c, 4.dp.toPx(), Offset(tx + 4.dp.toPx(), yy + l.size.height / 2f))
                            tx += dotSpace
                        }
                        drawText(l, topLeft = Offset(tx, yy))
                        yy += l.size.height + gap
                    }
                }
            }
            if (series.size > 1) {
                Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    series.forEachIndexed { i, s ->
                        val off = i in hidden
                        LegendItem(s.name, colors[i], dimmed = off) {
                            hidden = if (off) hidden - i else hidden + i
                        }
                    }
                }
            }
            if (showChange && startV != null && endV != null) {
                val delta = endV - startV
                val rel = if (startV != 0.0) delta / abs(startV) else null
                val text = (if (delta > 0) "+" else "") + valueFormat(delta) + (rel?.let { " (" + pct(it) + ")" } ?: "")
                Row {
                    Text(
                        "Variation sur la période : ",
                        style = MaterialTheme.typography.bodySmall,
                        color = scheme.onSurfaceVariant,
                    )
                    Text(text, style = MaterialTheme.typography.bodySmall, fontWeight = FontWeight.Medium, color = gainColor(delta))
                }
            }
        }
    }
}

@Composable
fun StackedBarChart(
    groups: List<BarGroup>,
    modifier: Modifier = Modifier,
    height: Dp = 200.dp,
    limitLine: Double? = null,
    valueFormat: (Double) -> String = { euros(it) },
    selectedKey: String? = null,
    onGroupClick: (BarGroup) -> Unit = {},
) {
    if (groups.isEmpty()) {
        Muted("Rien à afficher.")
        return
    }
    val scheme = MaterialTheme.colorScheme
    val n = groups.size
    val cats = remember(groups) { groups.flatMap { g -> g.parts.map { it.first } }.toSortedSet().toList() }
    val palette = chartPalette(cats.size)
    val totals = groups.map { g -> g.parts.sumOf { it.second } }
    val maxData = max(max(totals.maxOrNull() ?: 0.0, limitLine ?: 0.0), 1.0)
    val step = niceStep(maxData, 4)
    val yMax = max(ceil(maxData / step - 1e-9) * step, step)
    val ticks = (0..(yMax / step).roundToInt()).map { it * step }
    var tapped by remember(groups) { mutableStateOf<Int?>(null) }
    val currentGroups by rememberUpdatedState(groups)
    val currentClick by rememberUpdatedState(onGroupClick)
    val gridColor = scheme.outlineVariant
    val limitColor = scheme.onSurfaceVariant
    val axisStyle = TextStyle(fontSize = 10.sp, color = scheme.onSurfaceVariant)
    val measurer = rememberTextMeasurer()
    val fmtAxis = axisFormatter(valueFormat, null)

    val summary = "Barres empilées, ${n} périodes, de ${groups.first().label} à ${groups.last().label}. " +
        "Total le plus récent : ${valueFormat(totals.last())}."

    Column(modifier.fillMaxWidth().semantics { contentDescription = summary }, verticalArrangement = Arrangement.spacedBy(8.dp)) {
        val t = tapped?.takeIf { it in 0 until n }
        if (t != null) {
            val g = groups[t]
            ChartBubble {
                Column(Modifier.padding(horizontal = 10.dp, vertical = 8.dp), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                    Text("${g.label} · ${valueFormat(totals[t])}", style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.SemiBold)
                    g.parts.filter { it.second > 0 }.sortedByDescending { it.second }.take(3).forEach { (c, v) ->
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Dot(palette[cats.indexOf(c).coerceAtLeast(0)])
                            Spacer(Modifier.width(6.dp))
                            Text("$c : ${valueFormat(v)}", style = MaterialTheme.typography.labelMedium)
                        }
                    }
                }
            }
        }
        Row(Modifier.fillMaxWidth()) {
            // Axe Y fixe à gauche.
            Canvas(Modifier.width(44.dp).height(height)) {
                val topPad = 6.dp.toPx()
                val plotH = size.height - topPad
                ticks.forEach { tk ->
                    val yy = size.height - (tk / yMax * plotH).toFloat()
                    val lay = measurer.measure(fmtAxis(tk), axisStyle)
                    val ty = (yy - lay.size.height / 2f).coerceIn(0f, size.height - lay.size.height)
                    drawText(lay, topLeft = Offset(size.width - 6.dp.toPx() - lay.size.width, ty))
                }
            }
            BoxWithConstraints(Modifier.weight(1f)) {
                val minBar = 36.dp
                val contentW = if (minBar * n > maxWidth) minBar * n else maxWidth
                val scroll = rememberScrollState()
                LaunchedEffect(n, scroll.maxValue) { scroll.scrollTo(scroll.maxValue) }
                Column(Modifier.horizontalScroll(scroll).width(contentW)) {
                    Canvas(
                        Modifier
                            .fillMaxWidth()
                            .height(height)
                            .pointerInput(n) {
                                detectTapGestures { off ->
                                    val i = ((off.x / size.width) * n).toInt().coerceIn(0, n - 1)
                                    tapped = i
                                    currentClick(currentGroups[i])
                                }
                            },
                    ) {
                        val topPad = 6.dp.toPx()
                        val plotH = size.height - topPad
                        val slot = size.width / n
                        val bw = slot * 0.62f
                        fun yOf(v: Double) = size.height - (v / yMax * plotH).toFloat()
                        ticks.forEach { tk ->
                            drawLine(gridColor.copy(alpha = 0.35f), Offset(0f, yOf(tk)), Offset(size.width, yOf(tk)), strokeWidth = 1.dp.toPx())
                        }
                        groups.forEachIndexed { i, g ->
                            val dim = selectedKey != null && g.key != selectedKey
                            val alpha = if (dim) 0.33f else 1f
                            val left = i * slot + (slot - bw) / 2f
                            var bottom = size.height
                            val present = cats.indices.filter { ci -> g.parts.any { it.first == cats[ci] && it.second > 0 } }
                            present.forEachIndexed { pi, ci ->
                                val amount = g.parts.filter { it.first == cats[ci] }.sumOf { it.second }
                                val h = (amount / yMax * plotH).toFloat()
                                val isTop = pi == present.lastIndex
                                if (isTop) {
                                    val r = min(4.dp.toPx(), min(h, bw / 2f))
                                    val path = Path().apply {
                                        addRoundRect(
                                            RoundRect(
                                                left, bottom - h, left + bw, bottom,
                                                topLeftCornerRadius = CornerRadius(r), topRightCornerRadius = CornerRadius(r),
                                                bottomRightCornerRadius = CornerRadius.Zero, bottomLeftCornerRadius = CornerRadius.Zero,
                                            ),
                                        )
                                    }
                                    drawPath(path, palette[ci].copy(alpha = alpha))
                                } else {
                                    drawRect(palette[ci].copy(alpha = alpha), Offset(left, bottom - h), Size(bw, h))
                                }
                                bottom -= h
                            }
                        }
                        if (limitLine != null) {
                            val yy = yOf(limitLine)
                            drawLine(
                                limitColor.copy(alpha = 0.85f), Offset(0f, yy), Offset(size.width, yy),
                                strokeWidth = 1.dp.toPx(), pathEffect = PathEffect.dashPathEffect(floatArrayOf(10f, 8f)),
                            )
                        }
                    }
                    Row(Modifier.fillMaxWidth().padding(top = 4.dp)) {
                        groups.forEach { g ->
                            Text(
                                g.label,
                                Modifier.weight(1f),
                                style = MaterialTheme.typography.labelSmall.copy(fontSize = 10.sp),
                                color = scheme.onSurfaceVariant,
                                textAlign = TextAlign.Center,
                                maxLines = 1,
                                overflow = TextOverflow.Clip,
                            )
                        }
                    }
                }
            }
        }
        if (limitLine != null) Muted("Ligne pointillée : ${valueFormat(limitLine)}")
        if (cats.size > 1) {
            Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                cats.forEachIndexed { i, c -> LegendItem(c, palette[i]) }
            }
        }
    }
}

private class RingEntry(val label: String, val value: Double, val color: Color, val members: List<Int>)

@Composable
fun DonutChart(
    slices: List<Slice>,
    centerTitle: String,
    centerValue: String,
    modifier: Modifier = Modifier,
    size: Dp = 180.dp,
    valueFormat: (Double) -> String = { euros(it) },
    onSliceClick: (Slice) -> Unit = {},
    showLegend: Boolean = true,
) {
    val pos = slices.filter { it.value > 0 }
    val total = pos.sumOf { it.value }
    if (pos.isEmpty() || total <= 0) {
        Muted("Rien à afficher.")
        return
    }
    val scheme = MaterialTheme.colorScheme
    val palette = chartPalette(pos.size)
    val colors = pos.mapIndexed { i, s -> s.color ?: palette[i] }
    val entries = remember(slices, colors) {
        val all = pos.mapIndexed { i, s -> RingEntry(s.label, s.value, colors[i], listOf(i)) }
        if (pos.size > 8) {
            val small = all.filter { it.value / total < 0.02 }
            if (small.isEmpty()) all else {
                all.filter { it.value / total >= 0.02 } +
                    RingEntry("Autres", small.sumOf { it.value }, scheme.outline, small.flatMap { it.members })
            }
        } else all
    }
    var selected by remember(slices) { mutableStateOf<Int?>(null) }
    val currentEntries by rememberUpdatedState(entries)
    val currentClick by rememberUpdatedState(onSliceClick)
    val currentPos by rememberUpdatedState(pos)
    val sel = selected?.takeIf { it in entries.indices }
    val trackColor = scheme.surfaceVariant

    val summary = "Répartition : " + pos.take(5).joinToString(", ") { "${it.label} ${pct(it.value / total, sign = false, digits = 0)}" } +
        ". $centerTitle : $centerValue."

    Column(modifier.fillMaxWidth().semantics { contentDescription = summary }, verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Box(Modifier.align(Alignment.CenterHorizontally).size(size), contentAlignment = Alignment.Center) {
            Canvas(
                Modifier
                    .size(size)
                    .pointerInput(entries) {
                        detectTapGestures { off ->
                            val cx = this.size.width / 2f
                            val cy = this.size.height / 2f
                            val dx = off.x - cx
                            val dy = off.y - cy
                            val r = hypot(dx, dy)
                            val outerR = min(cx, cy)
                            val inner = (outerR - 6.dp.toPx()) * 2f / 3f
                            if (r < inner * 0.9f || r > outerR) return@detectTapGestures
                            val angle = ((Math.toDegrees(atan2(dy, dx).toDouble()) + 90.0 + 360.0) % 360.0)
                            var acc = 0.0
                            val es = currentEntries
                            val sum = es.sumOf { it.value }
                            for ((idx, e) in es.withIndex()) {
                                acc += e.value / sum * 360.0
                                if (angle <= acc) {
                                    selected = idx
                                    if (e.members.size == 1) currentClick(currentPos[e.members[0]])
                                    break
                                }
                            }
                        }
                    },
            ) {
                // Épaisseur = 1/3 du rayon ; la part touchée gagne de la place vers l'extérieur.
                val extra = 6.dp.toPx()
                val center = Offset(this.size.width / 2f, this.size.height / 2f)
                val outerBase = this.size.minDimension / 2f - extra
                val thick = outerBase / 3f
                val inner = outerBase - thick
                val baseR = inner + thick / 2f
                val bigThick = thick + extra
                val bigR = inner + bigThick / 2f
                drawCircle(trackColor.copy(alpha = 0.3f), baseR, center, style = Stroke(thick))
                val sum = entries.sumOf { it.value }
                var start = -90f
                entries.forEachIndexed { i, e ->
                    val sweep = (e.value / sum * 360.0).toFloat()
                    val gap = if (entries.size > 1) min(3f, sweep * 0.4f) else 0f
                    val isSel = i == sel
                    val rad = if (isSel) bigR else baseR
                    drawArc(
                        e.color, start + gap / 2f, sweep - gap, false,
                        Offset(center.x - rad, center.y - rad), Size(rad * 2f, rad * 2f),
                        style = Stroke(if (isSel) bigThick else thick),
                    )
                    start += sweep
                }
            }
            Column(Modifier.padding(horizontal = size * 0.24f), horizontalAlignment = Alignment.CenterHorizontally) {
                val e = sel?.let { entries[it] }
                Text(
                    e?.label ?: centerTitle,
                    style = MaterialTheme.typography.labelMedium,
                    color = scheme.onSurfaceVariant,
                    maxLines = 2,
                    textAlign = TextAlign.Center,
                    overflow = TextOverflow.Ellipsis,
                )
                Text(
                    e?.let { valueFormat(it.value) } ?: centerValue,
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold,
                    maxLines = 1,
                    textAlign = TextAlign.Center,
                )
            }
        }
        if (showLegend) pos.forEachIndexed { i, s ->
            val ringIdx = entries.indexOfFirst { i in it.members }
            Row(
                Modifier
                    .fillMaxWidth()
                    .clickable {
                        selected = ringIdx
                        onSliceClick(s)
                    }
                    .padding(vertical = 4.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Dot(colors[i])
                Spacer(Modifier.width(8.dp))
                Text(
                    s.label,
                    Modifier.weight(1f),
                    style = MaterialTheme.typography.bodyMedium,
                    fontWeight = if (sel != null && sel == ringIdx) FontWeight.SemiBold else FontWeight.Normal,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                Spacer(Modifier.width(8.dp))
                Text(valueFormat(s.value), style = MaterialTheme.typography.bodyMedium)
                Spacer(Modifier.width(8.dp))
                Text(
                    pct(s.value / total, sign = false, digits = 1),
                    Modifier.widthIn(min = 52.dp),
                    style = MaterialTheme.typography.bodySmall,
                    color = scheme.onSurfaceVariant,
                    textAlign = TextAlign.End,
                )
            }
        }
    }
}

@Composable
fun HorizontalBars(
    items: List<Slice>,
    modifier: Modifier = Modifier,
    valueFormat: (Double) -> String = { euros(it) },
    colorByTone: Boolean = false,
    onClick: (Slice) -> Unit = {},
) {
    if (items.isEmpty()) {
        Muted("Rien à afficher.")
        return
    }
    val scheme = MaterialTheme.colorScheme
    val gain = gainColor(1.0)
    val loss = gainColor(-1.0)
    val maxAbs = max(items.maxOf { abs(it.value) }, 1e-9)
    val mixed = colorByTone && items.any { it.value < 0 } && items.any { it.value > 0 }
    val palette = chartPalette(items.size)
    val track = scheme.surfaceVariant.copy(alpha = 0.4f)
    val axis = scheme.outline
    val summary = "Barres : " + items.take(5).joinToString(", ") { "${it.label} ${valueFormat(it.value)}" }

    Column(modifier.fillMaxWidth().semantics { contentDescription = summary }, verticalArrangement = Arrangement.spacedBy(4.dp)) {
        items.forEachIndexed { i, item ->
            val barColor = when {
                colorByTone -> if (item.value < 0) loss else if (item.value > 0) gain else scheme.onSurfaceVariant
                else -> item.color ?: palette[i]
            }
            Row(
                Modifier.fillMaxWidth().clickable { onClick(item) }.padding(vertical = 3.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    item.label,
                    Modifier.weight(0.34f),
                    style = MaterialTheme.typography.bodyMedium,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                Spacer(Modifier.width(8.dp))
                Canvas(Modifier.weight(0.38f).height(8.dp)) {
                    val r = CornerRadius(size.height / 2f)
                    drawRoundRect(track, Offset.Zero, size, r)
                    if (mixed) {
                        val half = size.width / 2f
                        val len = max((abs(item.value) / maxAbs * half).toFloat(), size.height)
                        if (item.value >= 0) drawRoundRect(barColor, Offset(half, 0f), Size(len, size.height), r)
                        else drawRoundRect(barColor, Offset(half - len, 0f), Size(len, size.height), r)
                        drawLine(axis, Offset(half, 0f), Offset(half, size.height), strokeWidth = 1.dp.toPx())
                    } else {
                        val len = max((abs(item.value) / maxAbs * size.width).toFloat(), size.height)
                        drawRoundRect(barColor, Offset.Zero, Size(len, size.height), r)
                    }
                }
                Spacer(Modifier.width(8.dp))
                Text(
                    valueFormat(item.value),
                    Modifier.weight(0.28f),
                    style = MaterialTheme.typography.bodyMedium,
                    fontWeight = FontWeight.Medium,
                    color = if (colorByTone) barColor else scheme.onSurface,
                    textAlign = TextAlign.End,
                    maxLines = 1,
                )
            }
        }
    }
}

@Composable
fun Sparkline(values: List<Double>, modifier: Modifier = Modifier, height: Dp = 28.dp) {
    val color = gainColor(if (values.size >= 2) values.last() - values.first() else null)
    Canvas(modifier.height(height).widthIn(min = 48.dp)) {
        if (values.size < 2) return@Canvas
        val lo = values.min()
        val hi = values.max()
        val span = if (hi - lo > 0) hi - lo else 1.0
        val pad = 2.dp.toPx()
        val h = size.height - 2 * pad
        val step = size.width / (values.size - 1)
        val path = Path()
        values.forEachIndexed { i, v ->
            val x = i * step
            val y = (pad + h * (1 - (v - lo) / span)).toFloat()
            if (i == 0) path.moveTo(x, y) else path.lineTo(x, y)
        }
        drawPath(path, color, style = Stroke(1.6.dp.toPx(), cap = StrokeCap.Round, join = StrokeJoin.Round))
    }
}

/**
 * Barre de fourchette (ex. plus bas / plus haut sur 52 semaines) avec des repères (cours, prix de revient,
 * objectif…). L'échelle s'élargit si un repère sort de la fourchette ; légende dessous.
 */
@Composable
fun RangeBar(
    low: Double,
    high: Double,
    markers: List<RangeMarker>,
    modifier: Modifier = Modifier,
    valueFormat: (Double) -> String = { euros(it) },
) {
    val scheme = MaterialTheme.colorScheme
    val sLo = min(low, markers.minOfOrNull { it.value } ?: low)
    val sHi = max(high, markers.maxOfOrNull { it.value } ?: high)
    val labelStyle = TextStyle(fontSize = 10.sp, color = scheme.onSurfaceVariant)
    val measurer = rememberTextMeasurer()
    val track = scheme.surfaceVariant.copy(alpha = 0.5f)
    val rangeColor = ACTIVE_BLUE.copy(alpha = 0.3f)
    val ring = scheme.surface
    val summary = "Fourchette de ${valueFormat(low)} à ${valueFormat(high)}. " +
        markers.joinToString(" ") { "${it.label} ${valueFormat(it.value)}." }

    Column(modifier.fillMaxWidth().semantics { contentDescription = summary }, verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Canvas(Modifier.fillMaxWidth().height(40.dp)) {
            val side = 10.dp.toPx()
            val x0 = side
            val x1 = size.width - side
            val width = max(x1 - x0, 1f)
            fun xOf(v: Double) = if (sHi > sLo) x0 + width * ((v - sLo) / (sHi - sLo)).toFloat() else x0 + width / 2f
            val cy = 12.dp.toPx()
            val th = 8.dp.toPx()
            val r = CornerRadius(th / 2f)
            drawRoundRect(track, Offset(x0, cy - th / 2f), Size(width, th), r)
            val rx0 = xOf(low)
            val rx1 = xOf(high)
            drawRoundRect(rangeColor, Offset(rx0, cy - th / 2f), Size(max(rx1 - rx0, th), th), r)
            for ((v, txt) in listOf(low to valueFormat(low), high to valueFormat(high))) {
                val lay = measurer.measure(txt, labelStyle)
                val x = (xOf(v) - lay.size.width / 2f).coerceIn(0f, max(0f, size.width - lay.size.width))
                drawText(lay, topLeft = Offset(x, cy + 14.dp.toPx()))
            }
            markers.forEach { m ->
                drawCircle(ring, 8.dp.toPx(), Offset(xOf(m.value), cy))
                drawCircle(m.color, 6.dp.toPx(), Offset(xOf(m.value), cy))
            }
        }
        Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            markers.forEach { m -> LegendItem("${m.label} ${valueFormat(m.value)}", m.color) }
        }
    }
}
