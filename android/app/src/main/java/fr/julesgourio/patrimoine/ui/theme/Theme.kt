package fr.julesgourio.patrimoine.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontVariation
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp
import fr.julesgourio.patrimoine.R

/** Palette de la maquette (docs/maquette/patrimoine-v3.html, bloc `:root`). Thème clair seul, pas de couleurs dynamiques. */
object Pt {
    val Fond = Color(0xFFF3F4F7)
    val Carte = Color(0xFFFFFFFF)
    val Encre = Color(0xFF0E1320)
    val Sub = Color(0xFF5A6272)
    val Mute = Color(0xFF6F7787)
    val Ligne = Color(0xFFE9EBF0)
    val Pastille = Color(0xFFECEEF2)

    val Nuit = Color(0xFF0E1320)
    val Nuit2 = Color(0xFF1A2132)
    val NuitLigne = Color(0xFF252D40)
    val NuitSub = Color(0xFF9CA5B8)

    val Hausse = Color(0xFF087F54)
    val Baisse = Color(0xFFC7382F)
    val HausseNuit = Color(0xFF4ADE9A)
    val BaisseNuit = Color(0xFFFF8D83)
    val HausseFond = Color(0xFFE3F4EC)
    val BaisseFond = Color(0xFFFBE9E7)

    val Accent = Color(0xFF2A78D6)
    /** Couleurs de série, dans l'ordre (comptes, types, répartitions). */
    val Series = listOf(
        Color(0xFF2A78D6), Color(0xFFEB6834), Color(0xFF1BAF7A),
        Color(0xFFEDA100), Color(0xFF6250D6), Color(0xFF9AA3B5),
    )
    fun serie(i: Int) = Series[i.mod(Series.size)]
}

/** Gains et pertes : couleurs fixes, lisibles sur fond clair et sur fond sombre. */
@Immutable
data class Money(val gain: Color, val loss: Color, val gainNight: Color = Pt.HausseNuit, val lossNight: Color = Pt.BaisseNuit)

val LocalMoney = staticCompositionLocalOf { Money(Pt.Hausse, Pt.Baisse) }

@OptIn(androidx.compose.ui.text.ExperimentalTextApi::class)
private val Inter = FontFamily(
    listOf(400, 500, 600, 700).map { w ->
        Font(R.font.inter, FontWeight(w), variationSettings = FontVariation.Settings(FontVariation.weight(w)))
    },
)

private fun TextStyle.inter(weight: FontWeight? = null) = copy(
    fontFamily = Inter, fontFeatureSettings = "tnum", fontWeight = weight ?: fontWeight, letterSpacing = 0.sp,
)

private fun typography(): Typography {
    val d = Typography()
    return Typography(
        displayLarge = d.displayLarge.inter(), displayMedium = d.displayMedium.inter(),
        displaySmall = d.displaySmall.inter(FontWeight.Bold),
        headlineLarge = d.headlineLarge.inter(FontWeight.Bold), headlineMedium = d.headlineMedium.inter(FontWeight.Bold),
        headlineSmall = d.headlineSmall.inter(FontWeight.Bold),
        titleLarge = d.titleLarge.inter(FontWeight.SemiBold), titleMedium = d.titleMedium.inter(FontWeight.SemiBold),
        titleSmall = d.titleSmall.inter(FontWeight.SemiBold),
        bodyLarge = d.bodyLarge.copy(fontSize = 15.sp, lineHeight = 20.sp).inter(),
        bodyMedium = d.bodyMedium.copy(fontSize = 14.sp, lineHeight = 19.sp).inter(),
        bodySmall = d.bodySmall.copy(fontSize = 12.sp, lineHeight = 16.sp).inter(FontWeight.Medium),
        labelLarge = d.labelLarge.inter(FontWeight.SemiBold), labelMedium = d.labelMedium.inter(FontWeight.SemiBold),
        labelSmall = d.labelSmall.inter(FontWeight.Medium),
    )
}

private val Scheme = lightColorScheme(
    primary = Pt.Encre, onPrimary = Color.White,
    secondary = Pt.Accent, onSecondary = Color.White,
    primaryContainer = Pt.Pastille, onPrimaryContainer = Pt.Encre,
    secondaryContainer = Pt.Pastille, onSecondaryContainer = Pt.Encre,
    background = Pt.Fond, onBackground = Pt.Encre,
    surface = Pt.Fond, onSurface = Pt.Encre, onSurfaceVariant = Pt.Sub,
    surfaceVariant = Pt.Pastille, outline = Pt.Mute, outlineVariant = Pt.Ligne,
    surfaceContainerLowest = Pt.Carte, surfaceContainerLow = Pt.Carte, surfaceContainer = Pt.Carte,
    surfaceContainerHigh = Pt.Pastille, surfaceContainerHighest = Pt.Pastille,
    surfaceTint = Color.Transparent, error = Pt.Baisse,
)

@Composable
fun PatrimoineTheme(content: @Composable () -> Unit) {
    CompositionLocalProvider(LocalMoney provides Money(Pt.Hausse, Pt.Baisse)) {
        MaterialTheme(colorScheme = Scheme, typography = typography(), content = content)
    }
}
