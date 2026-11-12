package fr.julesgourio.patrimoine.ui

import android.net.Uri

/** Every destination of the app. Tabs first, then the screens opened from them. */
object Routes {
    const val ACCUEIL = "accueil"
    const val PORTEFEUILLE = "portefeuille"
    const val DEPENSES = "depenses"
    const val ANALYSES = "analyses"
    const val PLUS = "plus"

    const val TITRE = "titre/{symbole}"
    const val ANALYSE = "analyse/{id}"
    const val ORDRES = "ordres"
    const val ALERTES = "alertes"
    const val REGLAGES = "reglages"
    const val CMB = "cmb"
    const val OPERATIONS = "operations"
    const val PROJECTION = "projection"

    /** Market detail of a line or idea: a Yahoo ticker (AIR.PA, NVDA) or an ISIN. */
    fun titre(symbole: String) = "titre/" + Uri.encode(symbole)
    fun analyse(id: Int) = "analyse/$id"
}
