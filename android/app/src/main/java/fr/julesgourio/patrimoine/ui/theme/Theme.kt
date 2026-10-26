package fr.julesgourio.patrimoine.ui.theme

import android.os.Build
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.dynamicDarkColorScheme
import androidx.compose.material3.dynamicLightColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext

/** Gains and losses keep fixed, readable colours whatever the wallpaper colours are. */
@Immutable
data class Money(val gain: Color, val loss: Color)

val LocalMoney = staticCompositionLocalOf { Money(Color(0xFF1B8A5A), Color(0xFFC62828)) }

@Composable
fun PatrimoineTheme(content: @Composable () -> Unit) {
    val dark = isSystemInDarkTheme()
    val context = LocalContext.current
    val colors = when {
        Build.VERSION.SDK_INT >= 31 -> if (dark) dynamicDarkColorScheme(context) else dynamicLightColorScheme(context)
        dark -> darkColorScheme()
        else -> lightColorScheme(primary = Color(0xFF1E3A5F))
    }
    val money = if (dark) Money(Color(0xFF6FD6A4), Color(0xFFFF8A80)) else Money(Color(0xFF1B8A5A), Color(0xFFC62828))
    androidx.compose.runtime.CompositionLocalProvider(LocalMoney provides money) {
        MaterialTheme(colorScheme = colors, content = content)
    }
}
