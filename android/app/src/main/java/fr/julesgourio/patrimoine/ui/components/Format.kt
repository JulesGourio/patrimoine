package fr.julesgourio.patrimoine.ui.components

import java.text.NumberFormat
import java.time.LocalDate
import java.time.OffsetDateTime
import java.time.format.DateTimeFormatter
import java.util.Locale
import kotlin.math.abs

private val FR = Locale.FRANCE

private const val FINE = "\u202F"
private const val MOINS = "\u2212"

private fun fmt(x: Double, digits: Int): String {
    val f = NumberFormat.getNumberInstance(FR).apply {
        maximumFractionDigits = digits
        minimumFractionDigits = digits
    }
    val s = f.format(x)
    // « -0 » ne s'écrit pas ; le signe moins est le vrai (U+2212), pas le tiret.
    return if (s.trimStart('-').all { it == '0' || it == ',' || it == '.' }) s.trimStart('-') else s.replace("-", MOINS)
}

/** 12 345 € (milliers séparés par une espace fine, sans centimes au-dessus de 1 000 €), 12,34 € en dessous. */
fun euros(x: Double?, sign: Boolean = false, cents: Boolean? = null): String {
    if (x == null) return "\u2014"
    val s = fmt(x, if (cents ?: (abs(x) < 1000)) 2 else 0) + FINE + "\u20AC"
    return if (sign && x > 0 && !s.startsWith("0" + FINE)) "+$s" else s
}

/** Valeur en milliers pour un axe : 30,7 k€. */
fun eurosK(x: Double): String = fmt(x / 1000, 1) + FINE + "k\u20AC"

/** A fraction as a percentage: 0.034 → « +3,4 % ». */
fun pct(x: Double?, sign: Boolean = true, digits: Int = 1): String {
    if (x == null) return "\u2014"
    val s = fmt(x * 100, digits) + FINE + "%"
    return if (sign && x > 0 && !s.startsWith("0" + FINE) && !s.startsWith("0,0" + FINE)) "+$s" else s
}

fun number(x: Double?, digits: Int = 2): String {
    if (x == null) return "—"
    return NumberFormat.getNumberInstance(FR).apply { maximumFractionDigits = digits }.format(x).replace("-", MOINS)
}

/** Large dollar amounts: 1,2 M$ or 350 k$. */
fun usd(x: Double?): String = when {
    x == null -> "—"
    abs(x) >= 1e9 -> number(x / 1e9, 1) + " Md$"
    abs(x) >= 1e6 -> number(x / 1e6, 1) + " M$"
    else -> number(x / 1e3, 0) + " k$"
}

/** « 26/10/2026 » from an ISO date or timestamp; the input unchanged if it is not one. */
fun day(iso: String?): String {
    if (iso.isNullOrBlank()) return "—"
    return try {
        val d = if (iso.length > 10) OffsetDateTime.parse(iso).toLocalDate() else LocalDate.parse(iso.take(10))
        d.format(DateTimeFormatter.ofPattern("dd/MM/yyyy", FR))
    } catch (e: Exception) {
        try {
            LocalDate.parse(iso.take(10)).format(DateTimeFormatter.ofPattern("dd/MM/yyyy", FR))
        } catch (e: Exception) {
            iso
        }
    }
}

/** « 26/10 à 07:31 » from an ISO timestamp. */
fun moment(iso: String?): String {
    if (iso.isNullOrBlank()) return "jamais"
    return try {
        OffsetDateTime.parse(iso).atZoneSameInstant(java.time.ZoneId.systemDefault())
            .format(DateTimeFormatter.ofPattern("dd/MM 'à' HH:mm", FR))
    } catch (e: Exception) {
        day(iso)
    }
}

private val MOIS_COURTS = listOf("janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc.")

/** « 12 nov. » ou « 12 nov. 2026 » depuis une date ISO ; vide si ce n'en est pas une. */
fun dateCourte(iso: String?, avecAnnee: Boolean = false): String {
    val d = try { LocalDate.parse(iso?.take(10)) } catch (e: Exception) { return "" }
    return "${d.dayOfMonth} ${MOIS_COURTS[d.monthValue - 1]}" + if (avecAnnee) " ${d.year}" else ""
}

/** « févr. 2025 » */
fun moisAnnee(annee: Int, mois: Int): String = "${MOIS_COURTS[(mois - 1).coerceIn(0, 11)]} $annee"

/** Initiales d'un nom : deux premiers mots, ou deux premières lettres. */
fun initiales(nom: String?): String {
    val mots = (nom ?: "").split(Regex("[^\\p{L}\\p{N}]+")).filter { it.isNotEmpty() }
    return when {
        mots.size >= 2 -> "" + mots[0].first() + mots[1].first()
        mots.size == 1 -> mots[0].take(2)
        else -> "?"
    }.uppercase(FR)
}
