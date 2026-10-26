package fr.julesgourio.patrimoine.ui.components

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp

/** A plain line with a light fill; the first and last dates and the min/max below it. */
@Composable
fun LineChart(points: List<Pair<String, Double>>, height: Dp = 160.dp, modifier: Modifier = Modifier) {
    if (points.size < 2) {
        Muted("Pas encore assez d'historique pour une courbe.")
        return
    }
    val line = MaterialTheme.colorScheme.primary
    val values = points.map { it.second }
    val min = values.min()
    val max = values.max()
    val span = (max - min).takeIf { it > 0 } ?: 1.0
    Column(modifier) {
        Canvas(Modifier.fillMaxWidth().height(height)) {
            val step = size.width / (points.size - 1)
            fun at(i: Int) = Offset(i * step, (size.height * (1 - (values[i] - min) / span)).toFloat())
            val path = Path().apply {
                moveTo(at(0).x, at(0).y)
                for (i in 1 until points.size) lineTo(at(i).x, at(i).y)
            }
            val fill = Path().apply {
                addPath(path)
                lineTo(size.width, size.height)
                lineTo(0f, size.height)
                close()
            }
            drawPath(fill, Brush.verticalGradient(listOf(line.copy(alpha = 0.25f), line.copy(alpha = 0f))))
            drawPath(path, line, style = Stroke(width = 2.5.dp.toPx(), cap = StrokeCap.Round))
        }
        Row(Modifier.fillMaxWidth()) {
            Muted(day(points.first().first))
            Spacer(Modifier.weight(1f))
            Muted("min ${euros(min)} · max ${euros(max)}")
            Spacer(Modifier.weight(1f))
            Muted(day(points.last().first))
        }
    }
}
