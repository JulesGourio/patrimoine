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
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import java.time.LocalDate
import kotlin.math.abs
import kotlin.math.atan2
import kotlin.math.hypot
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt

/** Une courbe : points = (date ISO yyyy-MM-dd, valeur), triés. */
data class ChartSeries(
    val name: String,
    val points: List<Pair<String, Double>>,
    val color: Color? = null,
    val dashed: Boolean = false,
)

/** Une barre empilée : parts = (catégorie, montant >= 0). */
data class BarGroup(val label: String, val parts: List<Pair<String, Double>>, val key: String? = null)

/** Une part d'anneau ou une ligne de barres horizontales. */
data class Slice(val label: String, val value: Double, val key: String? = null, val color: Color? = null)

private val BASE_PALETTE = listOf(
    Color(0xFF4C78A8), Color(0xFFF58518), Color(0xFF54A24B), Color(0xFFE45756), Color(0xFFB279A2),
    Color(0xFF72B7B2), Color(0xFFEECA3B), Color(0xFFFF9DA6), Color(0xFF9D755D), Color(0xFFBAB0AC),
)

/** Palette catégorielle stable (mêmes couleurs dans le même ordre), lisible en clair et en sombre. */
fun chartPalette(n: Int): List<Color> = List(max(n, 0)) { i ->
    if (i < BASE_PALETTE.size) BASE_PALETTE[i] else Color.hsv(((i * 47) % 360).toFloat(), 0.55f, 0.75f)
}

private fun parseDate(s: String): LocalDate? = try {
    LocalDate.parse(s.take(10))
} catch (e: Exception) {
    null
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

private val PERIODS = listOf("1 M" to 30L, "6 M" to 182L, "1 A" to 365L, "Tout" to null)

@Composable
private fun Pill(text: String, selected: Boolean, dot: Color? = null, dimmed: Boolean = false, onClick: () -> Unit) {
    val scheme = MaterialTheme.colorScheme
    val shape = RoundedCornerShape(50)
    Row(
        Modifier
            .clip(shape)
            .background(if (selected) scheme.secondaryContainer else Color.Transparent)
            .border(1.dp, scheme.outlineVariant, shape)
            .clickable(onClick = onClick)
            .padding(horizontal = 12.dp, vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        if (dot != null) {
            Box(Modifier.size(8.dp).clip(CircleShape).background(if (dimmed) dot.copy(alpha = 0.3f) else dot))
            Spacer(Modifier.width(6.dp))
        }
        Text(
            text,
            style = MaterialTheme.typography.labelMedium,
            color = if (dimmed) scheme.onSurfaceVariant.copy(alpha = 0.6f) else scheme.onSurface,
            maxLines = 1,
        )
    }
}

@Composable
private fun Dot(color: Color) {
    Box(Modifier.size(8.dp).clip(CircleShape).background(color))
}

@Composable
fun InteractiveLineChart(
    series: List<ChartSeries>,
    modifier: Modifier = Modifier,
    height: Dp = 200.dp,
    showPeriods: Boolean = true,
    stacked: Boolean = false,
    valueFormat: (Double) -> String = { euros(it) },
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

    val cursorColor = scheme.onSurfaceVariant
    val gridColor = scheme.outlineVariant
    val ringColor = scheme.surface

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
        if (series.size > 1) {
            Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                series.forEachIndexed { i, s ->
                    val off = i in hidden
                    Pill(s.name, selected = false, dot = colors[i], dimmed = off) {
                        hidden = if (off) hidden - i else hidden + i
                    }
                }
            }
        }
        if (n < 2) {
            Muted("Pas assez de points sur cette période.")
        } else {
            Row(Modifier.fillMaxWidth().height(height)) {
                Column(Modifier.height(height).padding(vertical = 1.dp), verticalArrangement = Arrangement.SpaceBetween) {
                    for (k in 0..3) {
                        Text(
                            valueFormat(hi - span * k / 3.0),
                            style = MaterialTheme.typography.labelSmall.copy(fontSize = 10.sp),
                            color = scheme.onSurfaceVariant,
                            maxLines = 1,
                        )
                    }
                }
                Spacer(Modifier.width(6.dp))
                Box(Modifier.weight(1f).height(height)) {
                    Canvas(
                        Modifier
                            .fillMaxWidth()
                            .height(height)
                            .pointerInput(n) {
                                detectTapGestures { off ->
                                    selRaw = ((off.x / size.width) * (n - 1)).roundToInt().coerceIn(0, n - 1)
                                }
                            }
                            .pointerInput(n) {
                                detectHorizontalDragGestures(
                                    onDragStart = { off ->
                                        selRaw = ((off.x / size.width) * (n - 1)).roundToInt().coerceIn(0, n - 1)
                                    },
                                ) { change, _ ->
                                    selRaw = ((change.position.x / size.width) * (n - 1)).roundToInt().coerceIn(0, n - 1)
                                    change.consume()
                                }
                            },
                    ) {
                        val pad = 8.dp.toPx()
                        val w = size.width
                        val plotH = size.height - 2 * pad
                        fun px(i: Int) = w * i / (n - 1)
                        fun py(v: Double) = (pad + plotH * (1 - (v - lo) / span)).toFloat()
                        for (k in 0..3) {
                            val yy = pad + plotH * k / 3f
                            drawLine(gridColor.copy(alpha = 0.5f), Offset(0f, yy), Offset(w, yy), strokeWidth = 1.dp.toPx())
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
                                val top = plotted[s]
                                val area = Path()
                                area.moveTo(px(0), py(top[0] ?: 0.0))
                                for (i in 1 until n) area.lineTo(px(i), py(top[i] ?: 0.0))
                                for (i in n - 1 downTo 0) area.lineTo(px(i), py(prev[i] ?: 0.0))
                                area.close()
                                drawPath(area, colors[s].copy(alpha = 0.55f))
                                prev = top
                            }
                            for (s in visible) {
                                drawPath(
                                    linePath(plotted[s]), colors[s],
                                    style = Stroke(1.5.dp.toPx(), cap = StrokeCap.Round, join = StrokeJoin.Round),
                                )
                            }
                        } else {
                            if (visible.size == 1) {
                                val s = visible[0]
                                val first = plotted[s].indexOfFirst { it != null }
                                val lastI = plotted[s].indexOfLast { it != null }
                                if (first in 0 until lastI) {
                                    val fill = Path().apply {
                                        addPath(linePath(plotted[s]))
                                        lineTo(px(lastI), size.height)
                                        lineTo(px(first), size.height)
                                        close()
                                    }
                                    drawPath(fill, Brush.verticalGradient(listOf(colors[s].copy(alpha = 0.22f), colors[s].copy(alpha = 0f))))
                                }
                            }
                            for (s in visible) {
                                val effect = if (series[s].dashed) PathEffect.dashPathEffect(floatArrayOf(14f, 10f)) else null
                                drawPath(
                                    linePath(plotted[s]), colors[s],
                                    style = Stroke(2.5.dp.toPx(), cap = StrokeCap.Round, join = StrokeJoin.Round, pathEffect = effect),
                                )
                            }
                        }
                        if (sel != null) {
                            val cx = px(sel)
                            drawLine(cursorColor.copy(alpha = 0.7f), Offset(cx, 0f), Offset(cx, size.height), strokeWidth = 1.dp.toPx())
                            for (s in visible) {
                                val v = plotted[s][sel] ?: continue
                                drawCircle(ringColor, 6.dp.toPx(), Offset(cx, py(v)))
                                drawCircle(colors[s], 4.dp.toPx(), Offset(cx, py(v)))
                            }
                        }
                    }
                    if (sel != null) {
                        val onRight = sel.toFloat() / (n - 1) < 0.5f
                        Surface(
                            modifier = Modifier.align(if (onRight) Alignment.TopEnd else Alignment.TopStart).padding(4.dp),
                            shape = RoundedCornerShape(8.dp),
                            color = scheme.surfaceContainerHighest,
                            shadowElevation = 2.dp,
                        ) {
                            Column(Modifier.padding(horizontal = 10.dp, vertical = 6.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                                Text(day(dates[sel]), style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.SemiBold)
                                var total = 0.0
                                for (s in visible) {
                                    val v = vals[s][sel]
                                    if (v != null) total += v
                                    Row(verticalAlignment = Alignment.CenterVertically) {
                                        Dot(colors[s])
                                        Spacer(Modifier.width(6.dp))
                                        Text(
                                            if (series.size > 1) "${series[s].name} : ${v?.let(valueFormat) ?: "—"}" else (v?.let(valueFormat) ?: "—"),
                                            style = MaterialTheme.typography.labelMedium,
                                        )
                                    }
                                }
                                if (stacked && visible.size > 1) {
                                    Text("Total : ${valueFormat(total)}", style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.SemiBold)
                                }
                            }
                        }
                    }
                }
            }
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Muted(day(dates.first()))
                Spacer(Modifier.weight(1f))
                Muted(day(dates.last()))
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
    val maxV = max(max(totals.maxOrNull() ?: 0.0, limitLine ?: 0.0), 1.0)
    var tapped by remember(groups) { mutableStateOf<Int?>(null) }
    val currentGroups by rememberUpdatedState(groups)
    val currentClick by rememberUpdatedState(onGroupClick)
    val limitColor = scheme.error
    val gridColor = scheme.outlineVariant

    val summary = "Barres empilées, ${n} périodes, de ${groups.first().label} à ${groups.last().label}. " +
        "Total le plus récent : ${valueFormat(totals.last())}."

    Column(modifier.fillMaxWidth().semantics { contentDescription = summary }, verticalArrangement = Arrangement.spacedBy(8.dp)) {
        val t = tapped?.takeIf { it in 0 until n }
        if (t != null) {
            val g = groups[t]
            Surface(shape = RoundedCornerShape(8.dp), color = scheme.surfaceContainerHighest, shadowElevation = 2.dp) {
                Column(Modifier.padding(horizontal = 10.dp, vertical = 6.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
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
        BoxWithConstraints(Modifier.fillMaxWidth()) {
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
                    val pad = 4.dp.toPx()
                    val plotH = size.height - pad
                    val slot = size.width / n
                    val bw = slot * 0.66f
                    drawLine(gridColor, Offset(0f, size.height), Offset(size.width, size.height), strokeWidth = 1.dp.toPx())
                    groups.forEachIndexed { i, g ->
                        val dim = selectedKey != null && g.key != selectedKey
                        val alpha = if (dim) 0.35f else 1f
                        val left = i * slot + (slot - bw) / 2f
                        var bottom = size.height
                        cats.forEachIndexed { ci, c ->
                            val amount = g.parts.filter { it.first == c }.sumOf { it.second }
                            if (amount > 0) {
                                val h = (amount / maxV * plotH).toFloat()
                                drawRect(palette[ci].copy(alpha = alpha), Offset(left, bottom - h), Size(bw, h))
                                bottom -= h
                            }
                        }
                    }
                    if (limitLine != null) {
                        val yy = (size.height - limitLine / maxV * plotH).toFloat()
                        drawLine(
                            limitColor, Offset(0f, yy), Offset(size.width, yy),
                            strokeWidth = 1.5.dp.toPx(), pathEffect = PathEffect.dashPathEffect(floatArrayOf(14f, 10f)),
                        )
                    }
                }
                Row(Modifier.fillMaxWidth()) {
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
        if (limitLine != null) Muted("Ligne pointillée : ${valueFormat(limitLine)}")
        if (cats.size > 1) {
            Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                cats.forEachIndexed { i, c ->
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Dot(palette[i])
                        Spacer(Modifier.width(4.dp))
                        Text(c, style = MaterialTheme.typography.labelSmall, color = scheme.onSurfaceVariant, maxLines = 1)
                    }
                }
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
                            if (r < min(cx, cy) * 0.4f || r > min(cx, cy)) return@detectTapGestures
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
                val base = 26.dp.toPx()
                val big = 34.dp.toPx()
                val inset = big / 2f
                val side = this.size.minDimension - 2 * inset
                val topLeft = Offset(inset, inset)
                val arcSize = Size(side, side)
                drawArc(trackColor.copy(alpha = 0.3f), 0f, 360f, false, topLeft, arcSize, style = Stroke(base))
                val sum = entries.sumOf { it.value }
                var start = -90f
                entries.forEachIndexed { i, e ->
                    val sweep = (e.value / sum * 360.0).toFloat()
                    val gap = if (entries.size > 1 && sweep > 2f) 1f else 0f
                    drawArc(
                        e.color, start + gap / 2f, sweep - gap, false, topLeft, arcSize,
                        style = Stroke(if (i == sel) big else base),
                    )
                    start += sweep
                }
            }
            Column(Modifier.padding(horizontal = size * 0.22f), horizontalAlignment = Alignment.CenterHorizontally) {
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
        pos.forEachIndexed { i, s ->
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

    Column(modifier.fillMaxWidth().semantics { contentDescription = summary }, verticalArrangement = Arrangement.spacedBy(6.dp)) {
        items.forEachIndexed { i, item ->
            val barColor = when {
                colorByTone -> if (item.value < 0) loss else if (item.value > 0) gain else scheme.onSurfaceVariant
                else -> item.color ?: if (items.size > 1) palette[i] else scheme.primary
            }
            Column(Modifier.fillMaxWidth().clickable { onClick(item) }.padding(vertical = 2.dp)) {
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        item.label,
                        Modifier.weight(1f),
                        style = MaterialTheme.typography.bodyMedium,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                    Spacer(Modifier.width(8.dp))
                    Text(
                        valueFormat(item.value),
                        style = MaterialTheme.typography.bodyMedium,
                        fontWeight = FontWeight.Medium,
                        color = if (colorByTone) barColor else scheme.onSurface,
                    )
                }
                Canvas(Modifier.fillMaxWidth().height(10.dp)) {
                    val r = size.height / 2f
                    drawRect(track, Offset(0f, 0f), size)
                    if (mixed) {
                        val half = size.width / 2f
                        val len = (abs(item.value) / maxAbs * half).toFloat()
                        if (item.value >= 0) drawRect(barColor, Offset(half, 0f), Size(len, size.height))
                        else drawRect(barColor, Offset(half - len, 0f), Size(len, size.height))
                        drawLine(axis, Offset(half, 0f), Offset(half, size.height), strokeWidth = 1.dp.toPx())
                    } else {
                        val len = (abs(item.value) / maxAbs * size.width).toFloat()
                        drawRect(barColor, Offset(0f, 0f), Size(max(len, r / 2f), size.height))
                    }
                }
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
        drawPath(path, color, style = Stroke(1.5.dp.toPx(), cap = StrokeCap.Round, join = StrokeJoin.Round))
    }
}
