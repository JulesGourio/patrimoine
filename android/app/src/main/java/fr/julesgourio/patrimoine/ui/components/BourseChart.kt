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
import fr.julesgourio.patrimoine.ui.theme.LocalMoney
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

    /**
     * Valeur en euros : aire dégradée, ligne de référence en pointillé si fournie (montant investi, prix de revient,
     * clôture précédente). [centimes] pour un cours unitaire ; [reperes] : achats et ventes posés sur la courbe.
     * Des dates de la forme « 2026-11-13T10:35 » donnent un axe en heures.
     */
    class Euros(override val dates: List<String>, val valeurs: List<Double>, val investi: List<Double>?, val hausse: Boolean,
                override val anneeAxe: Boolean, val centimes: Boolean = false, val reperes: List<Repere> = emptyList()) : ModeleBourse

    /** Rendement en fraction : portefeuille (blanc), indice (gris), ligne de zéro. */
    class Pourcent(override val dates: List<String>, val portefeuille: List<Double>, val indice: List<Double>?,
                   override val anneeAxe: Boolean) : ModeleBourse

    /** Aires empilées, une couleur par compte. */
    class Comptes(override val dates: List<String>, val piles: List<Pair<Color, List<Double>>>, override val anneeAxe: Boolean) : ModeleBourse
}

/** Un achat ou une vente de l'utilisateur, posé sur le point [index] de la courbe. */
class Repere(val index: Int, val achat: Boolean, val detail: String = "")

/** Couleurs des repères : achat (triangle vers le haut) et vente (triangle vers le bas), lisibles sur fond sombre. */
val CouleurAchat = Color(0xFF6CB2FF)
val CouleurVente = Color(0xFFFFB84D)

/** Heure « 10:35 » d'une date horodatée, sinon la date courte. */
private fun libelleAxe(iso: String, annee: Boolean) = if (iso.length > 10) iso.substring(11, 16) else dateCourte(iso, annee)

private const val MARGE_DROITE = 8f
private val HAUT = 30.dp   // bande du haut : l'infobulle y est dessinée (elle déborde un peu sur la courbe)
private val BAS = 172.dp
private val TOTAL = 192.dp

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

    val gain = LocalMoney.current.gain
    val perte = LocalMoney.current.loss
    Canvas(
        modifier.fillMaxWidth().height(TOTAL).pointerInput(modele) {
            awaitEachGesture {
                val down = awaitFirstDown(requireUnconsumed = false)
                val largeur = size.width - MARGE_DROITE.dp.toPx()
                fun indice(x: Float) = ((x / largeur).coerceIn(0f, 1f) * (n - 1)).roundToInt()
                val avant = survol
                var bouge = false
                survol = indice(down.position.x)
                do {
                    val ev = awaitPointerEvent()
                    val c = ev.changes.first()
                    survol = indice(c.position.x)
                    // Glissé horizontal : le graphique le garde ; vertical : la liste défile.
                    if (abs(c.positionChange().x) > abs(c.positionChange().y)) { c.consume(); bouge = true }
                } while (c.pressed)
                // L'infobulle reste après le doigt levé ; un second appui sur le même point la referme.
                if (!bouge && avant == survol) survol = null
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
        val enEchelle = modele is ModeleBourse.Euros && investiDansEchelle(modele)
        fun y(v: Double) = (bas - ((v - lo) / (if (hi - lo == 0.0) 1.0 else hi - lo)) * (bas - haut)).toFloat()
        fun ligne(v: List<Double>): Path = Path().apply {
            v.forEachIndexed { i, a -> if (i == 0) moveTo(x(i), y(a)) else lineTo(x(i), y(a)) }
        }

        var pointSurvol: Offset? = null
        when (modele) {
            is ModeleBourse.Euros -> {
                val c = if (modele.hausse) Pt.HausseNuit else Pt.BaisseNuit
                val p = ligne(modele.valeurs)
                val aire = Path().apply { addPath(p); lineTo(l, bas); lineTo(0f, bas); close() }
                drawPath(aire, Brush.verticalGradient(listOf(c.copy(alpha = 0.28f), c.copy(alpha = 0f)), startY = haut, endY = bas))
                modele.investi?.takeIf { enEchelle }?.let {
                    drawPath(ligne(it), Pt.NuitSub, style = Stroke(1.4.dp.toPx(), pathEffect = PathEffect.dashPathEffect(floatArrayOf(3.dp.toPx(), 4.dp.toPx()))))
                }
                drawPath(p, c, style = Stroke(2.dp.toPx(), join = StrokeJoin.Round, cap = StrokeCap.Round))
                val fin = Offset(l, y(modele.valeurs.last()))
                drawCircle(Pt.Nuit, 6.dp.toPx(), fin)
                drawCircle(c, 4.dp.toPx(), fin)
                modele.reperes.forEach { r ->
                    if (r.index in modele.valeurs.indices) repere(Offset(x(r.index), y(modele.valeurs[r.index])), r.achat, haut, bas, 0f, l)
                }
                survol?.let { pointSurvol = Offset(x(it), y(modele.valeurs[it])) }
            }
            is ModeleBourse.Pourcent -> {
                if (lo < 0.0 && hi > 0.0) {
                    val zy = y(0.0)
                    drawLine(Color(0xFF3A445C), Offset(0f, zy), Offset(size.width, zy), 1.dp.toPx(),
                        pathEffect = PathEffect.dashPathEffect(floatArrayOf(2.dp.toPx(), 3.dp.toPx())))
                }
                modele.indice?.let { drawPath(ligne(it), Pt.NuitSub, style = Stroke(1.6.dp.toPx(), join = StrokeJoin.Round)) }
                drawPath(ligne(modele.portefeuille), Color.White, style = Stroke(2.dp.toPx(), join = StrokeJoin.Round, cap = StrokeCap.Round))
                survol?.let { pointSurvol = Offset(x(it), y(modele.portefeuille[it])) }
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
                survol?.let { pointSurvol = Offset(x(it), y(cumul[it])) }
            }
        }

        // Axes : bornes à gauche, première et dernière dates en pied.
        val fmt = formatAxe(modele, lo, hi)
        etiquetteAxe(mesure, fmt(hi), Offset(6.dp.toPx(), haut + 1.dp.toPx()), axe)
        etiquetteAxe(mesure, fmt((lo + hi) / 2), Offset(6.dp.toPx(), (haut + bas) / 2 + 1.dp.toPx()), axe)
        etiquetteAxe(mesure, fmt(lo), Offset(6.dp.toPx(), bas - 14.dp.toPx()), axe)
        val pied = TOTAL.toPx() - 15.dp.toPx()
        val premier = libelleAxe(modele.dates.first(), modele.anneeAxe)
        val dernier = libelleAxe(modele.dates.last(), modele.anneeAxe)
        etiquetteAxe(mesure, premier, Offset(6.dp.toPx(), pied), axe)
        val fin = mesure.measure(dernier, axe)
        etiquetteAxe(mesure, dernier, Offset(size.width - 6.dp.toPx() - fin.size.width, pied), axe)

        pointSurvol?.let { p ->
            drawLine(Color.White.copy(alpha = 0.5f), Offset(p.x, haut), Offset(p.x, bas), 1.dp.toPx())
            drawCircle(Pt.Nuit, 6.5.dp.toPx(), p)
            drawCircle(Color.White, 4.5.dp.toPx(), p)
            val lignes = lignesBulle(modele, survol!!, gain, perte)
            bulle(mesure, lignes, p.x, bulleTexte, bulleDate)
        }
    }
}

/** Une ligne de l'infobulle : texte et couleur ([null] = couleur par défaut), en gras ou non. */
private class LigneBulle(val texte: String, val couleur: Color? = null, val gras: Boolean = false)

/** Contenu de l'infobulle au point [i] : date ou heure, valeur, variation depuis le début de la période, achats et ventes du jour. */
private fun lignesBulle(m: ModeleBourse, i: Int, gain: Color, perte: Color): List<LigneBulle> {
    val date = m.dates[i].let { if (it.length > 10) dateCourte(it, false) + " · " + it.substring(11, 16) else dateCourte(it, true) }
    fun variation(v: Double, debut: Double, cents: Boolean): LigneBulle {
        val d = v - debut
        val txt = euros(d, sign = true, cents = cents) + (if (debut != 0.0) " (" + pct(d / abs(debut), digits = 2) + ")" else "") + " depuis le début"
        return LigneBulle(txt, if (d >= 0) gain else perte)
    }
    return when (m) {
        is ModeleBourse.Euros -> buildList {
            add(LigneBulle(date))
            add(LigneBulle((if (m.centimes) "Cours " else "") + euros(m.valeurs[i], cents = m.centimes), gras = true))
            add(variation(m.valeurs[i], m.valeurs.first(), m.centimes))
            m.reperes.filter { it.index == i }.forEach {
                add(LigneBulle((if (it.achat) "Achat" else "Vente") + if (it.detail.isNotEmpty()) " " + it.detail else "", if (it.achat) CouleurAchat else CouleurVente))
            }
        }
        is ModeleBourse.Pourcent -> buildList {
            add(LigneBulle(date))
            add(LigneBulle("Portefeuille " + pct(m.portefeuille[i], digits = 2), if (m.portefeuille[i] >= 0) gain else perte, gras = true))
            m.indice?.getOrNull(i)?.let {
                add(LigneBulle("Indice " + pct(it, digits = 2) + " · écart " + pct(m.portefeuille[i] - it, digits = 2)))
            }
        }
        is ModeleBourse.Comptes -> {
            val total = m.piles.sumOf { it.second.getOrElse(i) { 0.0 } }
            val debut = m.piles.sumOf { it.second.getOrElse(0) { 0.0 } }
            listOf(LigneBulle(date), LigneBulle(euros(total, cents = false), gras = true), variation(total, debut, false))
        }
    }
}

/** Triangle d'achat (pointe en haut, sous la courbe) ou de vente (pointe en bas, au-dessus), cerné de la couleur du fond. */
private fun DrawScope.repere(sur: Offset, achat: Boolean, haut: Float, bas: Float, gauche: Float, droite: Float) {
    val r = 5.dp.toPx()
    // Sous la courbe pour un achat, au-dessus pour une vente ; de l'autre côté quand le bord du graphique (et son étiquette) gêne.
    val marge = 22.dp.toPx()
    var dy = (if (achat) 1 else -1) * 10.dp.toPx()
    if (sur.y + dy > bas - marge || sur.y + dy < haut + r) dy = -dy
    val c = Offset(sur.x.coerceIn(gauche + r * 1.4f, droite - r * 1.4f), (sur.y + dy).coerceIn(haut + r, bas - r))
    val s = if (achat) -1f else 1f   // sens de la pointe
    val tri = Path().apply {
        moveTo(c.x, c.y + s * r)
        lineTo(c.x + r * 1.15f, c.y - s * r * 0.8f)
        lineTo(c.x - r * 1.15f, c.y - s * r * 0.8f)
        close()
    }
    drawPath(tri, Pt.Nuit, style = Stroke(3.dp.toPx(), join = StrokeJoin.Round))
    drawPath(tri, if (achat) CouleurAchat else CouleurVente)
}

/** Marge de l'échelle autour du min et du max de la période affichée. */
private const val MARGE_ECHELLE = 0.08

/** La ligne de référence (investi, clôture précédente) n'entre dans l'échelle que si elle n'écrase pas la courbe. */
private fun investiDansEchelle(m: ModeleBourse.Euros): Boolean {
    val inv = m.investi ?: return false
    val lo = m.valeurs.min()
    val hi = m.valeurs.max()
    val ecart = max(hi - lo, abs(hi) * 0.005)
    return inv.all { it >= lo - ecart * 0.6 && it <= hi + ecart * 0.6 }
}

/** Échelle verticale : min et max de la série de la période affichée plus 8 %, jamais forcée à zéro (sauf piles de comptes). */
private fun bornes(m: ModeleBourse): Pair<Double, Double> {
    val tous = when (m) {
        is ModeleBourse.Euros -> m.valeurs + (if (investiDansEchelle(m)) m.investi.orEmpty() else emptyList())
        is ModeleBourse.Pourcent -> m.portefeuille + (m.indice ?: emptyList())
        is ModeleBourse.Comptes -> {
            val maxTotal = m.dates.indices.maxOf { i -> m.piles.sumOf { it.second.getOrElse(i) { 0.0 } } }
            return 0.0 to (if (maxTotal <= 0) 1.0 else maxTotal * (1 + MARGE_ECHELLE))
        }
    }
    val lo = tous.min()
    val hi = tous.max()
    // Courbe plate : une étendue minimale évite de diviser par zéro et d'écraser la ligne au milieu.
    val minimum = if (m is ModeleBourse.Pourcent) 0.002 else max(abs(hi) * 0.002, 0.01)
    val etendue = max(hi - lo, minimum)
    val pv = etendue * MARGE_ECHELLE
    val milieu = (hi + lo) / 2
    return (milieu - etendue / 2 - pv) to (milieu + etendue / 2 + pv)
}

/** Format des graduations : assez de précision pour que haut, milieu et bas restent distincts sur une période courte. */
private fun formatAxe(m: ModeleBourse, lo: Double, hi: Double): (Double) -> String {
    val etendue = hi - lo
    return when {
        m is ModeleBourse.Pourcent -> { v -> pct(v, digits = if (etendue < 0.02) 2 else 1) }
        m is ModeleBourse.Euros && m.centimes -> { v -> euros(v, cents = true) }
        etendue < 3000 -> { v -> euros(v, cents = etendue < 30) }
        else -> { v -> eurosK(v) }
    }
}

private fun DrawScope.bulle(mesure: TextMeasurer, lignes: List<LigneBulle>, xCentre: Float, sv: TextStyle, sd: TextStyle) {
    val mesures = lignes.map { l ->
        val st = (if (l.gras) sv else sd).let { if (l.couleur != null) it.copy(color = l.couleur) else it }
        mesure.measure(l.texte, st)
    }
    val pad = 8.dp.toPx()
    val w = mesures.maxOf { it.size.width } + 2 * pad
    val h = mesures.sumOf { it.size.height } + 2 * 4.dp.toPx()
    val x0 = (xCentre - w / 2).coerceIn(0f, max(0f, size.width - w))
    drawRoundRect(Color.White, Offset(x0, 0f), Size(w, h), CornerRadius(8.dp.toPx()))
    var y = 4.dp.toPx()
    mesures.forEach { m ->
        drawText(m, topLeft = Offset(x0 + pad, y))
        y += m.size.height
    }
}
