package fr.julesgourio.patrimoine.ui.components

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import fr.julesgourio.patrimoine.ui.theme.LocalMoney

@Composable
fun gainColor(x: Double?): Color = when {
    x == null || x == 0.0 -> MaterialTheme.colorScheme.onSurfaceVariant
    x > 0 -> LocalMoney.current.gain
    else -> LocalMoney.current.loss
}

@Composable
fun SectionCard(
    title: String? = null,
    modifier: Modifier = Modifier,
    onClick: (() -> Unit)? = null,
    content: @Composable ColumnScope.() -> Unit,
) {
    Card(
        modifier = modifier.fillMaxWidth().let { if (onClick != null) it.clickable(onClick = onClick) else it },
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceContainerLow),
    ) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            if (title != null) Text(title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
            content()
        }
    }
}

/** Label on the left, value on the right; the value coloured by [tone] (gain/loss) when given. */
@Composable
fun InfoRow(label: String, value: String, tone: Double? = null, sub: String? = null, onClick: (() -> Unit)? = null) {
    Row(
        Modifier.fillMaxWidth().let { if (onClick != null) it.clickable(onClick = onClick) else it }.padding(vertical = 2.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Text(label, style = MaterialTheme.typography.bodyLarge, maxLines = 2, overflow = TextOverflow.Ellipsis)
            if (sub != null) {
                Text(sub, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 2, overflow = TextOverflow.Ellipsis)
            }
        }
        Spacer(Modifier.width(12.dp))
        Text(value, style = MaterialTheme.typography.bodyLarge, fontWeight = FontWeight.Medium,
            color = if (tone != null) gainColor(tone) else MaterialTheme.colorScheme.onSurface)
    }
}

/** A big figure with its caption, as at the top of the home screen. */
@Composable
fun BigFigure(caption: String, value: String, detail: String? = null, tone: Double? = null) {
    Column {
        Text(caption, style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(value, style = MaterialTheme.typography.displaySmall, fontWeight = FontWeight.SemiBold)
        if (detail != null) Text(detail, style = MaterialTheme.typography.bodyMedium, color = gainColor(tone))
    }
}

/** Spent against a budget: a bar that turns red past 100 %. */
@Composable
fun BudgetBar(label: String, spent: Double, budget: Double?) {
    Column(Modifier.fillMaxWidth()) {
        Row(Modifier.fillMaxWidth()) {
            Text(label, Modifier.weight(1f), style = MaterialTheme.typography.bodyMedium)
            Text(euros(spent) + (budget?.let { " / " + euros(it) } ?: ""), style = MaterialTheme.typography.bodyMedium)
        }
        if (budget != null && budget > 0) {
            val ratio = (spent / budget).toFloat()
            Spacer(Modifier.height(4.dp))
            LinearProgressIndicator(
                progress = { ratio.coerceIn(0f, 1f) },
                modifier = Modifier.fillMaxWidth(),
                color = if (ratio > 1f) LocalMoney.current.loss else MaterialTheme.colorScheme.primary,
            )
        }
    }
}

@Composable
fun Muted(text: String) {
    Text(text, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
}
