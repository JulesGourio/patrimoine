package fr.julesgourio.patrimoine.ui.components

import java.text.NumberFormat
import java.time.LocalDate
import java.time.OffsetDateTime
import java.time.format.DateTimeFormatter
import java.util.Locale
import kotlin.math.abs

private val FR = Locale.FRANCE

/** 12 345 € (no cents above 1 000 €), 12,34 € below. */
fun euros(x: Double?, sign: Boolean = false, cents: Boolean? = null): String {
    if (x == null) return "—"
    val withCents = cents ?: (abs(x) < 1000)
    val f = NumberFormat.getNumberInstance(FR).apply {
        maximumFractionDigits = if (withCents) 2 else 0
        minimumFractionDigits = if (withCents) 2 else 0
    }
    val s = f.format(x) + " €"
    return if (sign && x > 0) "+$s" else s
}

/** A fraction as a percentage: 0.034 → « +3,4 % ». */
fun pct(x: Double?, sign: Boolean = true, digits: Int = 1): String {
    if (x == null) return "—"
    val f = NumberFormat.getNumberInstance(FR).apply {
        maximumFractionDigits = digits
        minimumFractionDigits = digits
    }
    val s = f.format(x * 100) + " %"
    return if (sign && x > 0) "+$s" else s
}

fun number(x: Double?, digits: Int = 2): String {
    if (x == null) return "—"
    return NumberFormat.getNumberInstance(FR).apply { maximumFractionDigits = digits }.format(x)
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
