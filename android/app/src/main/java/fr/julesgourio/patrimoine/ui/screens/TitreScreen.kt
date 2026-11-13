package fr.julesgourio.patrimoine.ui.screens

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBars
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import fr.julesgourio.patrimoine.engine.Engine
import fr.julesgourio.patrimoine.ui.components.Carte
import fr.julesgourio.patrimoine.ui.components.CarteEntete
import fr.julesgourio.patrimoine.ui.components.CallScreen
import fr.julesgourio.patrimoine.ui.components.CouleurAchat
import fr.julesgourio.patrimoine.ui.components.CouleurVente
import fr.julesgourio.patrimoine.ui.components.GraphiqueBourse
import fr.julesgourio.patrimoine.ui.components.GrilleIndicateurs
import fr.julesgourio.patrimoine.ui.components.Indicateur
import fr.julesgourio.patrimoine.ui.components.Load
import fr.julesgourio.patrimoine.ui.components.ModeleBourse
import fr.julesgourio.patrimoine.ui.components.PastilleVariation
import fr.julesgourio.patrimoine.ui.components.RangeBar
import fr.julesgourio.patrimoine.ui.components.RangeMarker
import fr.julesgourio.patrimoine.ui.components.Repere
import fr.julesgourio.patrimoine.ui.components.SelecteurPeriode
import fr.julesgourio.patrimoine.ui.components.dateCourte
import fr.julesgourio.patrimoine.ui.components.day
import fr.julesgourio.patrimoine.ui.components.euros
import fr.julesgourio.patrimoine.ui.components.list
import fr.julesgourio.patrimoine.ui.components.num
import fr.julesgourio.patrimoine.ui.components.number
import fr.julesgourio.patrimoine.ui.components.objOrNull
import fr.julesgourio.patrimoine.ui.components.pct
import fr.julesgourio.patrimoine.ui.components.rememberCall
import fr.julesgourio.patrimoine.ui.components.str
import fr.julesgourio.patrimoine.ui.components.usd
import fr.julesgourio.patrimoine.ui.theme.LocalMoney
import fr.julesgourio.patrimoine.ui.theme.Pt
import org.json.JSONObject
import java.time.Instant
import java.time.ZoneId

/** Fiche d'un titre : l'outil `titre` fournit tout en un appel ; `marche` (réseau) ajoute fondamentaux et actualités s'il répond. */

private val PERIODES = listOf("1J", "1S", "1M", "3M", "YTD", "1A", "MAX")
private val LEGENDE_PERIODE = mapOf(
    "1J" to "aujourd'hui", "1S" to "7 jours", "1M" to "1 mois", "3M" to "3 mois",
    "YTD" to "depuis le 1er janv.", "1A" to "1 an", "MAX" to "depuis l'origine",
)
private val ACHAT_CLAIR = Pt.Accent
private val VENTE_CLAIRE = Color(0xFFC98500)
private val COULEUR_OBJECTIF = Color(0xFF1BAF7A)
private const val OPERATIONS_VISIBLES = 5

private fun JSONObject.serie(): Pair<List<String>, List<Double>> {
    val a = optJSONArray("serie") ?: return emptyList<String>() to emptyList()
    val dates = ArrayList<String>(a.length())
    val vals = ArrayList<Double>(a.length())
    for (i in 0 until a.length()) {
        val p = a.optJSONArray(i) ?: continue
        if (p.isNull(1)) continue
        dates += p.optString(0)
        vals += p.optDouble(1)
    }
    return dates to vals
}

/** Date d'une actualité : texte ISO ou horodatage Unix (secondes). */
private fun dateActu(n: JSONObject): String {
    val brut = n.str("date") ?: return "—"
    val secondes = brut.toDoubleOrNull()
    return if (secondes != null && secondes > 1e9) {
        Instant.ofEpochSecond(secondes.toLong()).atZone(ZoneId.systemDefault()).toLocalDate().toString().let { day(it) }
    } else {
        day(brut)
    }
}

@Composable
fun TitreScreen(symbole: String, onBack: () -> Unit) {
    val state = rememberCall("titre", Engine.args("isin" to symbole), symbole)
    val marche = rememberCall("marche", Engine.args("titre" to symbole, "periode" to "1y"), symbole)
    var choix by rememberSaveable { mutableStateOf<String?>(null) }
    var toutVoir by rememberSaveable { mutableStateOf(false) }
    val titre = (state.load as? Load.Done)?.data
    val fondamentaux = (marche.load as? Load.Done)?.data

    Column(Modifier.fillMaxSize()) {
        EnTete(
            titre?.str("nom") ?: if (state.load is Load.Loading) "" else symbole,
            titre?.let { listOfNotNull(it.str("type"), it.str("symbole")).joinToString(" · ") },
            onBack,
        )
        Box(Modifier.weight(1f)) {
            CallScreen(state, PaddingValues(0.dp), horizontal = 0.dp) { t ->
                val periodes = t.objOrNull("periodes")
                val periode = choix ?: if (periodes?.objOrNull("1J")?.get("intraday") == true) "1J" else "1A"
                item { Box(Modifier.padding(horizontal = 16.dp)) { BlocCours(t, periode) { choix = it } } }
                item { Box(Modifier.padding(horizontal = 16.dp)) { CartePosition(t) } }
                item { Box(Modifier.padding(horizontal = 16.dp)) { CarteVariations(t) } }
                t.objOrNull("dividendes")?.let { d -> item { Box(Modifier.padding(horizontal = 16.dp)) { CarteDividendes(d) } } }
                if (t.list("operations").isNotEmpty()) {
                    item {
                        Box(Modifier.padding(horizontal = 16.dp)) {
                            CarteOperations(t.list("operations"), t.num("nb_operations")?.toInt() ?: 0, toutVoir) { toutVoir = !toutVoir }
                        }
                    }
                }
                if (fondamentaux != null) {
                    val devise = fondamentaux.str("currency")
                    val enEuros = devise == null || devise == "EUR"
                    fourchette(fondamentaux, t.num("pmp"), enEuros, devise)
                    item { Box(Modifier.padding(horizontal = 16.dp)) { CarteFondamentaux(fondamentaux, enEuros, devise) } }
                    val profil = listOfNotNull(fondamentaux.str("sector"), fondamentaux.str("industry"), fondamentaux.str("country"))
                    if (profil.isNotEmpty() || fondamentaux.str("activite") != null) {
                        item { Box(Modifier.padding(horizontal = 16.dp)) { CarteProfil(fondamentaux) } }
                    }
                    val actus = fondamentaux.list("actualites")
                    if (actus.isNotEmpty()) item { Box(Modifier.padding(horizontal = 16.dp)) { CarteActualites(actus) } }
                }
            }
        }
    }
}

// ---------- barre du haut ----------

@Composable
private fun EnTete(nom: String, sous: String?, onBack: () -> Unit) {
    Row(
        Modifier.fillMaxWidth().windowInsetsPadding(WindowInsets.statusBars).padding(horizontal = 16.dp).height(56.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Box(Modifier.size(40.dp).clip(CircleShape).background(Pt.Carte).clickable(onClick = onBack), contentAlignment = Alignment.Center) {
            Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Retour", Modifier.size(20.dp), tint = Pt.Encre)
        }
        Column(Modifier.weight(1f)) {
            Text(nom, fontSize = 20.sp, fontWeight = FontWeight.Bold, letterSpacing = (-0.3).sp, color = Pt.Encre, maxLines = 1, overflow = TextOverflow.Ellipsis)
            if (!sous.isNullOrBlank()) Text(sous, fontSize = 12.sp, fontWeight = FontWeight.Medium, color = Pt.Mute, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
    }
}

// ---------- bloc sombre ----------

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun BlocCours(t: JSONObject, periode: String, onPeriode: (String) -> Unit) {
    val money = LocalMoney.current
    val p = t.objOrNull("periodes")?.objOrNull(periode)
    val (dates, valeurs) = p?.serie() ?: (emptyList<String>() to emptyList())
    val pctP = p?.num("pct")
    val eurP = p?.num("eur")
    val ton = if ((eurP ?: 0.0) < 0) money.lossNight else money.gainNight
    val intraday = p?.get("intraday") == true && dates.size >= 2
    val pmp = t.num("pmp")
    val base = p?.num("base")
    val reference = if (periode == "1J") base else pmp
    val lo = valeurs.minOrNull()
    val hi = valeurs.maxOrNull()
    val marge = if (lo != null && hi != null) maxOf((hi - lo) * 0.5, hi * 0.02) else 0.0
    val dansEchelle = reference != null && lo != null && hi != null && reference >= lo - marge && reference <= hi + marge
    val reperes = remember(t, periode) { reperes(t.list("operations"), dates) }
    val modele = remember(t, periode) {
        if (!intraday) null
        else ModeleBourse.Euros(
            dates, valeurs, if (dansEchelle) List(dates.size) { reference!! } else null, (eurP ?: 0.0) >= 0,
            periode in listOf("1A", "MAX"), centimes = true, reperes = reperes,
        )
    }
    val achats = reperes.any { it.achat }
    val ventes = reperes.any { !it.achat }

    Column(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(24.dp)).background(Pt.Nuit).padding(top = 18.dp, bottom = 12.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Column(Modifier.fillMaxWidth().padding(horizontal = 18.dp)) {
            val dernier = if (periode == "1J" && dates.isNotEmpty() && dates.last().length > 10) "Cours · " + dates.last().substring(11, 16)
            else "Cours" + (t.str("date")?.let { " · " + dateCourte(it) } ?: "")
            Text(dernier, fontSize = 12.sp, fontWeight = FontWeight.Medium, color = Pt.NuitSub, maxLines = 1)
            Text(euros(t.num("cours"), cents = true), fontSize = 38.sp, fontWeight = FontWeight.Bold, letterSpacing = (-1.1).sp,
                color = Color.White, maxLines = 1, lineHeight = 42.sp)
        }
        FlowRow(
            Modifier.fillMaxWidth().padding(horizontal = 18.dp).offset(y = (-6).dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(4.dp),
            itemVerticalAlignment = Alignment.CenterVertically,
        ) {
            PastilleVariation(pctP, sombre = true)
            if (eurP != null) Text(euros(eurP, sign = true, cents = true), fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = ton)
            Text(LEGENDE_PERIODE[periode] ?: "", fontSize = 13.sp, fontWeight = FontWeight.Medium, color = Pt.NuitSub)
        }
        if (modele != null) {
            GraphiqueBourse(modele)
            Row(Modifier.fillMaxWidth().padding(horizontal = 18.dp)) {
                FlowRow(horizontalArrangement = Arrangement.spacedBy(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp),
                    itemVerticalAlignment = Alignment.CenterVertically) {
                    if (reference != null) {
                        LegendeTrait(
                            (if (periode == "1J") "Clôture préc." else "Prix de revient") + if (dansEchelle) "" else " (hors graphique)",
                            euros(reference, cents = true), pointille = true,
                        )
                    }
                    if (achats) LegendeRepere("Achat", true)
                    if (ventes) LegendeRepere("Vente", false)
                }
            }
        } else {
            Box(Modifier.fillMaxWidth().height(96.dp).padding(horizontal = 18.dp), contentAlignment = Alignment.Center) {
                Text(
                    if (periode == "1J" && p?.get("intraday") != true) "Cours intrajournaliers indisponibles" else "Pas assez d'historique",
                    fontSize = 12.sp, color = Pt.NuitSub,
                )
            }
        }
        SelecteurPeriode(PERIODES, periode, onPeriode)
    }
}

/** Achats et ventes qui tombent dans la fenêtre du graphique, posés sur le premier point à leur date ou après. */
private fun reperes(operations: List<JSONObject>, dates: List<String>): List<Repere> {
    if (dates.size < 2 || dates.first().length > 10) return emptyList()
    val debut = dates.first()
    val fin = dates.last()
    return operations.mapNotNull { o ->
        val sens = o.str("sens")
        val d = o.str("date")?.take(10)
        if ((sens != "achat" && sens != "vente") || d == null || d < debut || d > fin) return@mapNotNull null
        val i = dates.indexOfFirst { it >= d }
        if (i < 0) null else Repere(i, sens == "achat")
    }
}

@Composable
private fun LegendeTrait(libelle: String, valeur: String, pointille: Boolean) {
    Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
        Canvas(Modifier.width(12.dp).height(3.dp)) {
            val e = PathEffect.dashPathEffect(floatArrayOf(3.dp.toPx(), 2.dp.toPx()))
            drawLine(Pt.NuitSub, Offset(0f, size.height / 2), Offset(size.width, size.height / 2), 1.6.dp.toPx(),
                pathEffect = if (pointille) e else null)
        }
        Text(libelle, fontSize = 12.sp, color = Pt.NuitSub, maxLines = 1)
        Text(valeur, fontSize = 12.sp, fontWeight = FontWeight.SemiBold, color = Color.White, maxLines = 1)
    }
}

@Composable
private fun LegendeRepere(libelle: String, achat: Boolean) {
    Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
        Triangle(if (achat) CouleurAchat else CouleurVente, achat, 10.dp)
        Text(libelle, fontSize = 12.sp, color = Pt.NuitSub, maxLines = 1)
    }
}

/** Triangle plein : pointe en haut pour un achat, en bas pour une vente (mêmes formes que sur le graphique). */
@Composable
private fun Triangle(couleur: Color, haut: Boolean, taille: androidx.compose.ui.unit.Dp) {
    Canvas(Modifier.size(taille)) {
        val w = size.width
        val h = size.height
        val p = Path().apply {
            if (haut) { moveTo(w / 2, 0f); lineTo(w, h); lineTo(0f, h) } else { moveTo(0f, 0f); lineTo(w, 0f); lineTo(w / 2, h) }
            close()
        }
        drawPath(p, couleur)
    }
}

// ---------- cartes ----------

@Composable
private fun Filet() {
    Box(Modifier.fillMaxWidth().height(1.dp).background(Pt.Ligne))
}

/** Libellé à gauche, valeur à droite (et une ligne discrète dessous), séparée de la précédente par un filet fin. */
@Composable
private fun LigneValeur(
    libelle: String, valeur: String, tonValeur: Color = Pt.Encre, sousLibelle: String? = null, sousValeur: String? = null,
    tonSous: Color = Pt.Mute, separateur: Boolean = true,
) {
    Column {
        if (separateur) Filet()
        Row(Modifier.fillMaxWidth().padding(vertical = 10.dp), verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Column(Modifier.weight(1f)) {
                Text(libelle, fontSize = 14.sp, color = Pt.Sub, maxLines = 1, overflow = TextOverflow.Ellipsis)
                if (sousLibelle != null) Text(sousLibelle, fontSize = 12.sp, color = Pt.Mute, maxLines = 1)
            }
            Column(horizontalAlignment = Alignment.End) {
                Text(valeur, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = tonValeur, maxLines = 1)
                if (sousValeur != null) Text(sousValeur, fontSize = 12.sp, fontWeight = FontWeight.SemiBold, color = tonSous, maxLines = 1)
            }
        }
    }
}

@Composable
private fun CartePosition(t: JSONObject) {
    val money = LocalMoney.current
    val pos = t.objOrNull("position")
    Carte {
        CarteEntete("Ta position")
        if (pos == null) {
            Text("Titre non détenu", fontSize = 14.sp, color = Pt.Sub)
            return@Carte
        }
        val pv = pos.num("plus_value")
        val pvPct = pos.num("plus_value_pct")
        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(euros(pos.num("valeur"), cents = false), fontSize = 30.sp, fontWeight = FontWeight.Bold, letterSpacing = (-0.8).sp,
                color = Pt.Encre, maxLines = 1)
            if (pv != null) {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                    PastilleVariation(pvPct)
                    Text(euros(pv, sign = true, cents = false), fontSize = 14.sp, fontWeight = FontWeight.SemiBold,
                        color = if (pv < 0) money.loss else money.gain)
                    Text("plus-value", fontSize = 13.sp, fontWeight = FontWeight.Medium, color = Pt.Mute)
                }
            } else {
                Text("Prix de revient inconnu", fontSize = 13.sp, fontWeight = FontWeight.Medium, color = Pt.Mute)
            }
        }
        val jour = pos.num("variation_jour")
        Column {
            LigneValeur("Quantité", number(pos.num("quantite"), 4), separateur = false)
            LigneValeur("Prix de revient unitaire", euros(pos.num("pmp"), cents = true))
            LigneValeur("Montant investi", euros(pos.num("investi"), cents = false))
            LigneValeur("Variation du jour", if (jour == null) "—" else euros(jour, sign = true, cents = true),
                tonValeur = if (jour == null) Pt.Encre else if (jour < 0) money.loss else money.gain)
            LigneValeur("Poids dans le portefeuille", pct(pos.num("poids"), sign = false, digits = 1))
            val comptes = pos.list("comptes")
            if (comptes.size <= 1) {
                comptes.firstOrNull()?.let { LigneValeur("Compte", it.str("nom") ?: "—") }
            } else {
                comptes.forEach { c ->
                    val gain = c.num("plus_value")
                    LigneValeur(
                        c.str("nom") ?: "—", euros(c.num("valeur"), cents = false),
                        sousLibelle = number(c.num("quantite"), 4) + " titres",
                        sousValeur = gain?.let { euros(it, sign = true, cents = false) + " · " + pct(c.num("plus_value_pct")) },
                        tonSous = if ((gain ?: 0.0) < 0) money.loss else money.gain,
                    )
                }
            }
        }
    }
}

@Composable
private fun CarteVariations(t: JSONObject) {
    val v = t.objOrNull("variations")
    val risque = t.objOrNull("risque")
    fun ind(libelle: String, cle: String): Indicateur {
        val x = v?.objOrNull(cle)
        val p = x?.num("pct")
        return Indicateur(libelle, pct(p, digits = 2), x?.num("eur")?.let { euros(it, sign = true, cents = true) }, ton = p)
    }
    Carte {
        CarteEntete("Variations", "cours, par titre")
        GrilleIndicateurs(
            listOf(
                ind("Jour", "1J"), ind("7 jours", "1S"), ind("1 mois", "1M"), ind("3 mois", "3M"),
                ind("Depuis le 1er janv.", "YTD"), ind("1 an", "1A"),
                Indicateur("Volatilité sur 1 an", pct(risque?.num("volatilite"), sign = false, digits = 1)),
                Indicateur("Plus forte baisse", pct(risque?.num("plus_forte_baisse"), digits = 1), "sur 1 an",
                    ton2 = if (risque?.num("plus_forte_baisse") != null) Pt.Baisse else null),
            ),
        )
    }
}

@Composable
private fun CarteDividendes(d: JSONObject) {
    val dernier = d.objOrNull("dernier")
    Carte {
        CarteEntete("Dividendes")
        GrilleIndicateurs(
            listOf(
                Indicateur("Total reçu", euros(d.num("total"), cents = true), d.num("nb")?.toInt()?.let { "$it versement${if (it > 1) "s" else ""}" }),
                Indicateur("Dernier versement", euros(dernier?.num("montant"), cents = true), dernier?.str("date")?.let { day(it) }),
            ),
        )
    }
}

@Composable
private fun CarteOperations(ops: List<JSONObject>, total: Int, toutVoir: Boolean, onBasculer: () -> Unit) {
    val money = LocalMoney.current
    val affichees = if (toutVoir) ops else ops.take(OPERATIONS_VISIBLES)
    Carte {
        CarteEntete("Opérations", if (total > 0) total.toString() else null)
        Column {
            affichees.forEachIndexed { i, o ->
                val sens = o.str("sens")
                val couleur = when (sens) { "achat" -> ACHAT_CLAIR; "vente" -> VENTE_CLAIRE; else -> money.gain }
                if (i > 0) Filet()
                Row(Modifier.fillMaxWidth().padding(vertical = 9.dp), verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    Box(Modifier.size(34.dp).clip(RoundedCornerShape(10.dp)).background(Pt.Pastille), contentAlignment = Alignment.Center) {
                        when (sens) {
                            "achat" -> Triangle(couleur, true, 11.dp)
                            "vente" -> Triangle(couleur, false, 11.dp)
                            else -> Text("€", fontSize = 14.sp, fontWeight = FontWeight.Bold, color = couleur)
                        }
                    }
                    Column(Modifier.weight(1f)) {
                        Text(when (sens) { "achat" -> "Achat"; "vente" -> "Vente"; else -> "Dividende" }, fontSize = 14.sp,
                            fontWeight = FontWeight.SemiBold, color = Pt.Encre, maxLines = 1)
                        val q = o.num("quantite")
                        val px = o.num("prix")
                        if (q != null && px != null) {
                            Text(number(q, 4) + " × " + euros(px, cents = true), fontSize = 12.sp, color = Pt.Mute, maxLines = 1, overflow = TextOverflow.Ellipsis)
                        }
                    }
                    Column(horizontalAlignment = Alignment.End) {
                        Text(
                            (if (sens == "dividende") euros(o.num("montant"), sign = true, cents = true) else euros(o.num("montant"), cents = true)),
                            fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = if (sens == "dividende") money.gain else Pt.Encre, maxLines = 1,
                        )
                        Text(day(o.str("date")), fontSize = 12.sp, color = Pt.Mute, maxLines = 1)
                    }
                }
            }
        }
        if (total > OPERATIONS_VISIBLES) {
            Text(
                if (toutVoir) "Réduire" else "Tout voir ($total)", Modifier.fillMaxWidth().clickable(onClick = onBasculer).padding(vertical = 4.dp),
                fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = Pt.Accent, textAlign = TextAlign.Center,
            )
        }
    }
}

// ---------- données de marché (réseau) : cartes ajoutées si `marche` répond ----------

private fun androidx.compose.foundation.lazy.LazyListScope.fourchette(d: JSONObject, pmp: Double?, enEuros: Boolean, devise: String?) {
    val bas = d.num("fiftyTwoWeekLow")
    val haut = d.num("fiftyTwoWeekHigh")
    if (bas == null || haut == null) return
    val objectif = d.num("targetMeanPrice")
    val prix: (Double?) -> String = { x -> if (x == null) "—" else if (enEuros) euros(x, cents = true) else number(x) + " " + devise }
    item {
        Box(Modifier.padding(horizontal = 16.dp)) {
            Carte {
                CarteEntete("Fourchette 52 semaines", prix(bas) + " → " + prix(haut))
                val marqueurs = listOfNotNull(
                    d.num("dernier_cours")?.let { RangeMarker("Cours", it, Pt.Encre) },
                    // Le prix de revient est en euros : il n'a de sens que sur une cotation en euros.
                    if (enEuros) pmp?.let { RangeMarker("Prix de revient", it, Color(0xFFEDA100)) } else null,
                    objectif?.let { RangeMarker("Objectif", it, COULEUR_OBJECTIF) },
                )
                RangeBar(bas, haut, marqueurs, valueFormat = { prix(it) })
                val reco = d.str("recommendationKey")
                if (objectif != null || reco != null) {
                    Text(
                        listOfNotNull(
                            objectif?.let { "Objectif moyen " + prix(it) },
                            d.num("numberOfAnalystOpinions")?.let { number(it, 0) + " avis" },
                            reco?.let { "« $it »" },
                        ).joinToString(" · "),
                        fontSize = 12.sp, color = Pt.Mute,
                    )
                }
            }
        }
    }
}

@Composable
private fun CarteFondamentaux(d: JSONObject, enEuros: Boolean, devise: String?) {
    val money = LocalMoney.current
    val cap = d.num("marketCap")
    val croissance = d.num("revenueGrowth")
    Carte {
        CarteEntete("Fondamentaux")
        Column {
            LigneValeur("PER (réel / prévu)", number(d.num("trailingPE"), 1) + " / " + number(d.num("forwardPE"), 1), separateur = false)
            // Yahoo donne le rendement en pourcentage déjà (0,41 = 0,41 %).
            LigneValeur("Rendement du dividende", d.num("dividendYield")?.let { number(it) + " %" } ?: "—")
            LigneValeur("Croissance du CA", pct(croissance), tonValeur = if (croissance == null) Pt.Encre else if (croissance < 0) money.loss else money.gain)
            LigneValeur("Marge nette", pct(d.num("profitMargins"), sign = false))
            LigneValeur("Bêta", number(d.num("beta")))
            LigneValeur(
                "Capitalisation",
                when {
                    cap == null -> "—"
                    devise == "USD" -> usd(cap)
                    enEuros -> number(cap / 1e9, 0) + " Md€"
                    else -> number(cap / 1e9, 0) + " Md " + devise
                },
            )
        }
    }
}

@Composable
private fun CarteProfil(d: JSONObject) {
    Carte {
        CarteEntete("Profil")
        Column {
            var premier = true
            for ((libelle, valeur) in listOf("Secteur" to d.str("sector"), "Industrie" to d.str("industry"), "Pays" to d.str("country"))) {
                if (valeur != null) {
                    LigneValeur(libelle, valeur, separateur = !premier)
                    premier = false
                }
            }
        }
        d.str("activite")?.let { Text(it, fontSize = 14.sp, color = Pt.Sub, lineHeight = 19.sp) }
    }
}

@Composable
private fun CarteActualites(actus: List<JSONObject>) {
    Carte {
        CarteEntete("Actualités")
        Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            for (n in actus) {
                Column {
                    Text(n.str("titre") ?: "—", fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = Pt.Encre)
                    Text((n.str("source") ?: "source inconnue") + " · " + dateActu(n), fontSize = 12.sp, color = Pt.Mute)
                }
            }
        }
    }
}
