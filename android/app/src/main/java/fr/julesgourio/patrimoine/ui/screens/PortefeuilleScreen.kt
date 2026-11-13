package fr.julesgourio.patrimoine.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
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
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Search
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
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.lerp
import androidx.compose.ui.graphics.luminance
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.navigation.NavController
import fr.julesgourio.patrimoine.ui.Routes
import fr.julesgourio.patrimoine.ui.components.BarreRepartition
import fr.julesgourio.patrimoine.ui.components.CallScreen
import fr.julesgourio.patrimoine.ui.components.Carte
import fr.julesgourio.patrimoine.ui.components.CarteEntete
import fr.julesgourio.patrimoine.ui.components.Filtre
import fr.julesgourio.patrimoine.ui.components.GraphiqueBourse
import fr.julesgourio.patrimoine.ui.components.GrilleIndicateurs
import fr.julesgourio.patrimoine.ui.components.Indicateur
import fr.julesgourio.patrimoine.ui.components.InfoRow
import fr.julesgourio.patrimoine.ui.components.LigneListe
import fr.julesgourio.patrimoine.ui.components.LigneRepartition
import fr.julesgourio.patrimoine.ui.components.Loaded
import fr.julesgourio.patrimoine.ui.components.ModeleBourse
import fr.julesgourio.patrimoine.ui.components.Muted
import fr.julesgourio.patrimoine.ui.components.PastilleVariation
import fr.julesgourio.patrimoine.ui.components.PastillesFiltre
import fr.julesgourio.patrimoine.ui.components.SelecteurPeriode
import fr.julesgourio.patrimoine.ui.components.Segmente
import fr.julesgourio.patrimoine.ui.components.day
import fr.julesgourio.patrimoine.ui.components.euros
import fr.julesgourio.patrimoine.ui.components.initiales
import fr.julesgourio.patrimoine.ui.components.list
import fr.julesgourio.patrimoine.ui.components.moisAnnee
import fr.julesgourio.patrimoine.ui.components.num
import fr.julesgourio.patrimoine.ui.components.objOrNull
import fr.julesgourio.patrimoine.ui.components.pct
import fr.julesgourio.patrimoine.ui.components.rememberCall
import fr.julesgourio.patrimoine.ui.components.str
import fr.julesgourio.patrimoine.ui.theme.LocalMoney
import fr.julesgourio.patrimoine.ui.theme.Pt
import org.json.JSONArray
import org.json.JSONObject
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min

/** Écran Bourse (maquette docs/maquette) : tout vient de l'outil `bourse`, un seul appel. */

private val PERIODES = listOf("1J", "1S", "1M", "3M", "YTD", "1A", "MAX")
private val LEGENDE_PERIODE = mapOf(
    "1J" to "aujourd'hui", "1S" to "7 jours", "1M" to "1 mois", "3M" to "3 mois",
    "YTD" to "depuis le 1er janv.", "1A" to "1 an", "MAX" to "depuis l'origine",
)
private val SEUIL_TEINTE = mapOf("1J" to 2.0, "1S" to 3.0, "1M" to 10.0, "3M" to 20.0, "YTD" to 25.0, "1A" to 30.0, "MAX" to 35.0)
private val DIMENSIONS = listOf("compte" to "Compte", "type" to "Type", "secteur" to "Secteur", "pays" to "Pays", "devise" to "Devise")
private val COULEURS_LIGNES = listOf(0xFF3B4A6B, 0xFF2A78D6, 0xFF6250D6, 0xFF0E8A8A, 0xFFC98500, 0xFFD55181, 0xFF1BAF7A, 0xFFEB6834)
private val GRIS_NEUTRE = Color(0xFFEEF0F3)

private fun JSONObject.points(key: String): Pair<List<String>, List<Double>> {
    val a: JSONArray = optJSONArray(key) ?: return emptyList<String>() to emptyList()
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

private fun vueChoisie(data: JSONObject, compte: String): JSONObject? =
    if (compte == "tous") data.objOrNull("tous") else data.objOrNull("par_compte")?.objOrNull(compte) ?: data.objOrNull("tous")

private fun JSONObject.periode(p: String): JSONObject? = objOrNull("periodes")?.objOrNull(p)

@Composable
fun PortefeuilleScreen(nav: NavController) {
    val state = rememberCall("bourse")
    var compte by rememberSaveable { mutableStateOf("tous") }
    var periode by rememberSaveable { mutableStateOf("1J") }
    var mode by rememberSaveable { mutableStateOf("eur") }
    var tri by rememberSaveable { mutableStateOf("var") }
    var dimension by rememberSaveable { mutableStateOf("compte") }

    CallScreen(state, PaddingValues(0.dp), horizontal = 0.dp) { data ->
        val comptes = data.list("comptes")
        val vue = vueChoisie(data, compte)
        item { EnTete(onAjouter = { nav.navigate(Routes.AJOUTER) }) }
        if (vue == null) {
            item { Box(Modifier.padding(horizontal = 16.dp)) { Vide("Aucune position détenue.") } }
            item { Box(Modifier.padding(horizontal = 16.dp)) { VentesRealisees() } }
            return@CallScreen
        }
        val couleurs = comptes.mapIndexed { i, c -> (c.str("id") ?: "") to Pt.serie(i) }.toMap()
        item {
            val filtres = listOf(Filtre("tous", "Tous les comptes")) +
                comptes.map { Filtre(it.str("id") ?: "", it.str("nom") ?: "—", couleurs[it.str("id")]) }
            PastillesFiltre(filtres, if (vueChoisie(data, compte) === data.objOrNull("tous")) "tous" else compte, onChoix = { compte = it })
        }
        item {
            Box(Modifier.padding(horizontal = 16.dp)) {
                BlocPrincipal(data, vue, couleurs, periode, mode, { periode = it }, { mode = it })
            }
        }
        item { Box(Modifier.padding(horizontal = 16.dp)) { CartePerformance(vue, data.objOrNull("indice")) } }
        item { Box(Modifier.padding(horizontal = 16.dp)) { CartePositions(vue, periode, tri, { tri = it }, nav) } }
        if (vue.list("rendements_mensuels").isNotEmpty()) {
            item { Box(Modifier.padding(horizontal = 16.dp)) { CarteRendements(vue.list("rendements_mensuels")) } }
        }
        val rep = vue.objOrNull("repartition")
        if (rep != null) {
            item { Box(Modifier.padding(horizontal = 16.dp)) { CarteRepartition(rep, dimension) { dimension = it } } }
        }
        vue.objOrNull("dividendes_12m")?.let { d -> item { Box(Modifier.padding(horizontal = 16.dp)) { CarteDividendes(d, vue.str("prochain_versement")) } } }
        item { Box(Modifier.padding(horizontal = 16.dp)) { VentesRealisees() } }
    }
}

@Composable
private fun Vide(texte: String) {
    Carte { Text(texte, fontSize = 14.sp, color = Pt.Sub) }
}

// ---------- en-tête ----------

@Composable
private fun EnTete(onAjouter: () -> Unit) {
    Row(
        Modifier.fillMaxWidth().windowInsetsPadding(WindowInsets.statusBars).padding(horizontal = 16.dp).height(44.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text("Bourse", Modifier.weight(1f), fontSize = 26.sp, fontWeight = FontWeight.Bold, letterSpacing = (-0.5).sp, color = Pt.Encre)
        Box(Modifier.size(40.dp).clip(CircleShape).background(Pt.Carte).clickable { }, contentAlignment = Alignment.Center) {
            Icon(Icons.Filled.Search, contentDescription = "Rechercher", Modifier.size(20.dp), tint = Pt.Encre)
        }
        Spacer(Modifier.width(6.dp))
        Box(Modifier.size(40.dp).clip(CircleShape).background(Pt.Encre).clickable(onClick = onAjouter), contentAlignment = Alignment.Center) {
            Icon(Icons.Filled.Add, contentDescription = "Ajouter", Modifier.size(20.dp), tint = Color.White)
        }
    }
}

// ---------- bloc sombre ----------

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun BlocPrincipal(
    data: JSONObject,
    vue: JSONObject,
    couleurs: Map<String, Color>,
    periode: String,
    mode: String,
    onPeriode: (String) -> Unit,
    onMode: (String) -> Unit,
) {
    val money = LocalMoney.current
    val p = vue.periode(periode)
    val variation = p?.num("variation")
    val variationPct = p?.num("variation_pct")
    val baisse = (variation ?: 0.0) < 0
    val ton = if (baisse) money.lossNight else money.gainNight
    val (dates, valeurs) = p?.points("serie") ?: (emptyList<String>() to emptyList())
    val intraday = p?.get("intraday") == true
    val modele = remember(vue.str("id"), periode, mode, data) { modele(data, vue, p, periode, mode, couleurs) }

    Column(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(24.dp)).background(Pt.Nuit).padding(top = 18.dp, bottom = 12.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Row(Modifier.fillMaxWidth().padding(horizontal = 18.dp), verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Column(Modifier.weight(1f)) {
                val nb = vue.num("nb_comptes")?.toInt() ?: 0
                val nl = vue.num("nb_lignes")?.toInt() ?: 0
                val surtitre = if (vue.str("id") == "tous") "$nb compte${if (nb > 1) "s" else ""} · $nl ligne${if (nl > 1) "s" else ""}"
                else vue.str("nom") ?: ""
                Text(surtitre, fontSize = 12.sp, fontWeight = FontWeight.Medium, color = Pt.NuitSub, maxLines = 1, overflow = TextOverflow.Ellipsis)
                Text(euros(vue.num("valeur"), cents = false), fontSize = 38.sp, fontWeight = FontWeight.Bold, letterSpacing = (-1.1).sp,
                    color = Color.White, maxLines = 1, lineHeight = 42.sp)
            }
            Segmente(listOf("eur" to "€", "pct" to "%", "comptes" to "Comptes"), mode, onMode, sombre = true)
        }
        FlowRow(
            Modifier.fillMaxWidth().padding(horizontal = 18.dp).offset(y = (-6).dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(4.dp),
            itemVerticalAlignment = Alignment.CenterVertically,
        ) {
            PastilleVariation(variationPct, sombre = true)
            if (variation != null) Text(euros(variation, sign = true, cents = false), fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = ton)
            val hors = periode in listOf("1M", "3M", "YTD", "1A")
            Text((LEGENDE_PERIODE[periode] ?: "") + if (hors) " · hors versements" else "", fontSize = 13.sp, fontWeight = FontWeight.Medium, color = Pt.NuitSub)
        }
        if (modele != null) {
            GraphiqueBourse(modele)
            Row(Modifier.fillMaxWidth().padding(horizontal = 18.dp)) {
                FlowRow(horizontalArrangement = Arrangement.spacedBy(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    legende(data, vue, p, mode, couleurs, ton, dates, valeurs, periode)
                }
            }
        } else {
            Box(Modifier.fillMaxWidth().height(96.dp).padding(horizontal = 18.dp), contentAlignment = Alignment.Center) {
                Text(
                    if (periode == "1J" && !intraday) "Cours intrajournaliers indisponibles" else "Pas assez d'historique",
                    fontSize = 12.sp, color = Pt.NuitSub,
                )
            }
        }
        SelecteurPeriode(PERIODES, periode, onPeriode)
    }
}

private fun modele(data: JSONObject, vue: JSONObject, p: JSONObject?, periode: String, mode: String, couleurs: Map<String, Color>): ModeleBourse? {
    if (p == null || p.get("intraday") != true) return null
    val (dates, valeurs) = p.points("serie")
    if (dates.size < 2) return null
    val annee = periode in listOf("1A", "MAX")
    return when (mode) {
        "pct" -> {
            val (_, pf) = p.points("serie_pct")
            val (_, ix) = p.points("indice_serie")
            if (pf.size != dates.size) null else ModeleBourse.Pourcent(dates, pf, ix.takeIf { it.size == dates.size }, annee)
        }
        "comptes" -> {
            val c = p.objOrNull("comptes")
            val ordre = data.list("comptes").mapNotNull { it.str("id") }.filter { (vue.str("id") == "tous") || it == vue.str("id") }
            val piles = ordre.mapNotNull { id ->
                val v = c?.points(id)?.second.orEmpty()
                if (v.size == dates.size) (couleurs[id] ?: Pt.Series[5]) to v else null
            }
            if (piles.isEmpty()) null else ModeleBourse.Comptes(dates, piles, annee)
        }
        else -> {
            // En 1J, la ligne pointillée est la valeur à la clôture précédente.
            val inv = if (periode == "1J") p.num("cloture_precedente")?.let { c -> List(dates.size) { c } }
            else p.points("investi").second.takeIf { it.size == dates.size && periode in listOf("YTD", "1A", "MAX") }
            ModeleBourse.Euros(dates, valeurs, inv, (p.num("variation") ?: 0.0) >= 0, annee)
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun legende(
    data: JSONObject, vue: JSONObject, p: JSONObject?, mode: String, couleurs: Map<String, Color>, ton: Color,
    dates: List<String>, valeurs: List<Double>, periode: String,
) {
    when (mode) {
        "pct" -> {
            ItemLegende(Color.White, "Portefeuille", pct(p?.num("variation_pct"), digits = 2))
            val ind = data.objOrNull("indice")
            if (p?.num("indice_pct") != null) ItemLegende(Pt.NuitSub, ind?.str("nom") ?: "Indice", pct(p.num("indice_pct"), digits = 2))
        }
        "comptes" -> {
            val c = p?.objOrNull("comptes")
            data.list("comptes").filter { vue.str("id") == "tous" || it.str("id") == vue.str("id") }.forEach { a ->
                val v = c?.points(a.str("id") ?: "")?.second?.lastOrNull()
                ItemLegende(couleurs[a.str("id")] ?: Pt.Series[5], a.str("nom") ?: "—", euros(v, cents = false), carre = true)
            }
        }
        else -> {
            ItemLegende(ton, "Valeur", null)
            val inv = p?.points("investi")?.second.orEmpty()
            if (periode in listOf("YTD", "1A", "MAX") && inv.size == dates.size && inv.isNotEmpty()) ItemLegende(Pt.NuitSub, "Investi", euros(inv.last(), cents = false))
            else if (periode == "1J" && p?.num("cloture_precedente") != null) ItemLegende(Pt.NuitSub, "Clôture préc.", euros(p.num("cloture_precedente"), cents = false))
            else if (valeurs.isNotEmpty()) {
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text("Ouverture", fontSize = 12.sp, color = Pt.NuitSub)
                    Text(euros(valeurs.first(), cents = false), fontSize = 12.sp, fontWeight = FontWeight.SemiBold, color = Color.White)
                }
            }
        }
    }
}

@Composable
private fun ItemLegende(couleur: Color, libelle: String, valeur: String?, carre: Boolean = false) {
    Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.width(10.dp).height(if (carre) 8.dp else 3.dp).clip(RoundedCornerShape(2.dp)).background(couleur))
        Text(libelle, fontSize = 12.sp, color = Pt.NuitSub, maxLines = 1)
        if (valeur != null) Text(valeur, fontSize = 12.sp, fontWeight = FontWeight.SemiBold, color = Color.White, maxLines = 1)
    }
}

// ---------- performance ----------

@Composable
private fun CartePerformance(vue: JSONObject, indice: JSONObject?) {
    val gain = vue.num("gain_total")
    val investi = vue.num("investi")
    val ind = vue.objOrNull("indice")
    val nomIndice = indice?.str("nom") ?: "indice"
    val rend = vue.num("rendement_annualise")
    Carte {
        CarteEntete("Performance", "depuis l'origine")
        GrilleIndicateurs(
            listOf(
                Indicateur(
                    "Gain total", euros(gain, sign = true, cents = false),
                    if (gain != null && investi != null && investi > 0) "${pct(vue.num("gain_total_pct"), digits = 2)} sur ${euros(investi, cents = false)} investis"
                    else if (gain == null) "coût d'achat inconnu" else null,
                    ton = gain,
                ),
                Indicateur("Rendement annualisé", pct(rend), ind?.num("rendement_annualise")?.let { "$nomIndice ${pct(it)}" }, ton = rend),
                Indicateur("Volatilité sur 1 an", pct(vue.num("volatilite"), sign = false), ind?.num("volatilite")?.let { "$nomIndice ${pct(it, sign = false)}" }),
                Indicateur("Plus forte baisse", pct(vue.num("plus_forte_baisse")), "du plus haut au plus bas", ton2 = if (vue.num("plus_forte_baisse") != null) Pt.Baisse else null),
            ),
        )
        val lignes = listOf(
            Triple("Plus-values latentes", vue.num("plus_value_latente"), false),
            Triple("Plus-values réalisées", vue.num("plus_value_realisee"), false),
            Triple("Dividendes", vue.num("dividendes"), false),
            Triple("Dont frais", vue.num("frais")?.let { -it }, false),
            Triple("Gain total", gain, true),
        ).filter { it.second != null }
        Cascade(lignes.map { Triple(it.first, it.second!!, it.third) })
    }
}

@Composable
private fun Cascade(lignes: List<Triple<String, Double, Boolean>>) {
    if (lignes.isEmpty()) return
    val mn = min(0.0, lignes.minOf { it.second })
    val mx = max(0.0, lignes.maxOf { it.second })
    val etendue = (mx - mn).takeIf { it > 0 } ?: 1.0
    val z = ((0 - mn) / etendue).toFloat()
    val money = LocalMoney.current
    Column(verticalArrangement = Arrangement.spacedBy(9.dp)) {
        lignes.forEach { (titre, v, total) ->
            if (total) Box(Modifier.fillMaxWidth().height(1.dp).background(Pt.Ligne))
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Text(titre, Modifier.width(140.dp), fontSize = 13.sp, fontWeight = if (total) FontWeight.SemiBold else FontWeight.Normal,
                    color = if (total) Pt.Encre else Pt.Sub, maxLines = 1, overflow = TextOverflow.Ellipsis)
                val couleur = if (v < 0) money.loss else money.gain
                Box(
                    Modifier.weight(1f).height(10.dp).drawBehind {
                        val zx = z * size.width
                        drawLine(Pt.Ligne, Offset(zx, -4.dp.toPx()), Offset(zx, size.height + 4.dp.toPx()), 1.dp.toPx())
                        val w = max((abs(v) / etendue).toFloat() * size.width, 0.008f * size.width)
                        drawRoundRect(couleur, Offset(if (v < 0) zx - w else zx, 0f), Size(w, size.height), CornerRadius(3.dp.toPx()))
                    },
                )
                Text(euros(v, sign = true, cents = false), Modifier.width(66.dp), textAlign = TextAlign.End,
                    fontSize = if (total) 15.sp else 13.sp, fontWeight = FontWeight.SemiBold,
                    color = if (total) couleur else Pt.Encre, maxLines = 1, softWrap = false)
            }
        }
    }
}

// ---------- positions ----------

private fun teinte(pct: Double?, cap: Double): Pair<Color, Color> {
    if (pct == null) return GRIS_NEUTRE to Pt.Encre
    val t = 0.18 + 0.82 * min(1.0, abs(pct) * 100 / cap)
    val bg = lerp(GRIS_NEUTRE, if (pct < 0) Pt.Baisse else Pt.Hausse, t.toFloat())
    // Texte blanc ou encre selon le meilleur contraste (la teinte moyenne est trop claire pour du blanc).
    val clair = bg.luminance()
    return bg to if ((1.05) / (clair + 0.05) >= (clair + 0.05) / (Pt.Encre.luminance() + 0.05)) Color.White else Pt.Encre
}

private class Cellule(val ligne: JSONObject, val x: Double, val y: Double, val w: Double, val h: Double)

private fun decouper(items: List<JSONObject>, x: Double, y: Double, w: Double, h: Double, ratio: Double, out: MutableList<Cellule>) {
    if (items.isEmpty()) return
    if (items.size == 1) { out += Cellule(items[0], x, y, w, h); return }
    val somme = items.sumOf { it.num("valeur") ?: 0.0 }
    var acc = 0.0
    var k = 0
    while (k < items.size - 1 && acc + (items[k].num("valeur") ?: 0.0) <= somme / 2 + 1) { acc += items[k].num("valeur") ?: 0.0; k++ }
    if (k == 0) { acc = items[0].num("valeur") ?: 0.0; k = 1 }
    val f = acc / somme
    if (w * ratio >= h) {
        decouper(items.subList(0, k), x, y, w * f, h, ratio, out)
        decouper(items.subList(k, items.size), x + w * f, y, w * (1 - f), h, ratio, out)
    } else {
        decouper(items.subList(0, k), x, y, w, h * f, ratio, out)
        decouper(items.subList(k, items.size), x, y + h * f, w, h * (1 - f), ratio, out)
    }
}

private fun JSONObject.varPeriode(p: String): Pair<Double?, Double?> {
    val v = objOrNull("variation")?.objOrNull(p)
    return v?.num("pct") to v?.num("eur")
}

@Composable
private fun CartePositions(vue: JSONObject, periode: String, tri: String, onTri: (String) -> Unit, nav: NavController) {
    val lignes = vue.list("positions")
    Carte {
        CarteEntete("Positions", droite = {
            Segmente(listOf("var" to "Variation", "val" to "Valeur", "gain" to "Gain"), tri, onTri)
        })
        if (lignes.isEmpty()) {
            Text("Aucune position dans ce compte.", fontSize = 14.sp, color = Pt.Sub)
            return@Carte
        }
        TreemapPositions(lignes, periode)
        val tries = when (tri) {
            "val" -> lignes.sortedByDescending { it.num("valeur") ?: Double.NEGATIVE_INFINITY }
            "gain" -> lignes.sortedByDescending { it.num("plus_value") ?: Double.NEGATIVE_INFINITY }
            else -> lignes.sortedByDescending { it.varPeriode(periode).first ?: Double.NEGATIVE_INFINITY }
        }
        Column {
            tries.forEachIndexed { i, l ->
                val (pc, eur) = l.varPeriode(periode)
                val nom = l.str("nom") ?: l.str("isin") ?: "—"
                val cible = l.str("isin")
                LigneListe(
                    initiales(nom), Color(COULEURS_LIGNES[abs((l.str("isin") ?: nom).hashCode()) % COULEURS_LIGNES.size]), nom,
                    l.str("compte_nom"), euros(l.num("valeur"), cents = false),
                    if (pc == null) "—" else (if (eur != null) euros(eur, sign = true, cents = false) + " · " else "") + pct(pc, digits = 2),
                    tonDroite = pc, separateur = i > 0,
                    onClick = if (cible != null) ({ nav.navigate(Routes.titre(cible)) }) else null,
                )
            }
        }
    }
}

@Composable
private fun TreemapPositions(lignes: List<JSONObject>, periode: String) {
    val items = lignes.filter { (it.num("valeur") ?: 0.0) > 0 }.sortedByDescending { it.num("valeur") }
    if (items.isEmpty()) return
    val cap = SEUIL_TEINTE[periode] ?: 20.0
    BoxWithConstraints(Modifier.fillMaxWidth().height(200.dp).clip(RoundedCornerShape(12.dp))) {
        val cellules = remember(items, maxWidth) {
            val out = mutableListOf<Cellule>()
            decouper(items, 0.0, 0.0, 100.0, 100.0, maxWidth.value / (200.0 * 0.95), out)
            out
        }
        cellules.forEach { c ->
            val pc = c.ligne.varPeriode(periode).first
            val (bg, fg) = teinte(pc, cap)
            val minuscule = c.w < 17 || c.h < 26
            val moyen = c.w < 34
            val nom = c.ligne.str("nom") ?: "—"
            val forme = RoundedCornerShape(6.dp)
            Column(
                Modifier.offset(maxWidth * (c.x / 100).toFloat(), maxHeight * (c.y / 100).toFloat())
                    .size(maxWidth * (c.w / 100).toFloat(), maxHeight * (c.h / 100).toFloat())
                    .clip(forme).background(bg).border(1.dp, Pt.Carte, forme)
                    .padding(if (minuscule) 5.dp else 8.dp),
                verticalArrangement = if (minuscule) Arrangement.Center else Arrangement.SpaceBetween,
                horizontalAlignment = if (minuscule) Alignment.CenterHorizontally else Alignment.Start,
            ) {
                Text(if (moyen) initiales(nom) else nom, fontSize = 12.sp, fontWeight = FontWeight.SemiBold, color = fg, maxLines = 1,
                    overflow = TextOverflow.Ellipsis)
                if (!minuscule) Text(pct(pc, digits = if (moyen) 1 else 2), fontSize = 12.sp, fontWeight = FontWeight.SemiBold, color = fg, maxLines = 1)
            }
        }
    }
}

// ---------- rendements mensuels ----------

private val LETTRES_MOIS = listOf("J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D")

@Composable
private fun CarteRendements(mois: List<JSONObject>) {
    val parAnnee = mois.groupBy { it.num("annee")?.toInt() ?: 0 }.toSortedMap()
    val annees = parAnnee.keys.toList().takeLast(3)
    val affiches = mois.filter { (it.num("annee")?.toInt() ?: 0) in annees && it.num("rendement") != null }
    val meilleur = affiches.maxByOrNull { it.num("rendement") ?: -9.0 }
    val pire = affiches.minByOrNull { it.num("rendement") ?: 9.0 }
    val money = LocalMoney.current
    Carte {
        CarteEntete("Rendements mensuels", "en %")
        Column(verticalArrangement = Arrangement.spacedBy(3.dp)) {
            Row(horizontalArrangement = Arrangement.spacedBy(3.dp)) {
                Spacer(Modifier.width(36.dp))
                LETTRES_MOIS.forEach { Text(it, Modifier.weight(1f), fontSize = 11.sp, color = Pt.Mute, textAlign = TextAlign.Center, maxLines = 1) }
                Spacer(Modifier.width(52.dp))
            }
            annees.forEach { a ->
                val m = parAnnee[a].orEmpty().associate { (it.num("mois")?.toInt() ?: 0) to it.num("rendement") }
                val total = m.values.filterNotNull().fold(1.0) { t, r -> t * (1 + r) } - 1
                Row(horizontalArrangement = Arrangement.spacedBy(3.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text(a.toString(), Modifier.width(36.dp), fontSize = 12.sp, fontWeight = FontWeight.SemiBold, color = Pt.Encre, maxLines = 1)
                    for (i in 1..12) {
                        val r = m[i]
                        Box(Modifier.weight(1f).height(22.dp).clip(RoundedCornerShape(5.dp))
                            .background(if (r == null) Pt.Fond else teinte(r, 6.0).first))
                    }
                    Text(if (m.values.any { it != null }) pct(total) else "", Modifier.width(52.dp), fontSize = 12.sp, fontWeight = FontWeight.SemiBold,
                        textAlign = TextAlign.End, maxLines = 1, softWrap = false, color = if (total < 0) money.loss else money.gain)
                }
            }
        }
        meilleur?.let { Paire("Meilleur mois", pct(it.num("rendement")), money.gain, moisAnnee(it.num("annee")!!.toInt(), it.num("mois")!!.toInt())) }
        pire?.let { Paire("Pire mois", pct(it.num("rendement")), money.loss, moisAnnee(it.num("annee")!!.toInt(), it.num("mois")!!.toInt())) }
    }
}

@Composable
private fun Paire(libelle: String, valeur: String, couleur: Color, suite: String? = null) {
    Row(Modifier.fillMaxWidth()) {
        Text(libelle, Modifier.weight(1f), fontSize = 13.sp, color = Pt.Sub)
        Text(valeur, fontSize = 13.sp, fontWeight = FontWeight.SemiBold, color = couleur)
        if (suite != null) Text(" · $suite", fontSize = 13.sp, fontWeight = FontWeight.SemiBold, color = Pt.Encre)
    }
}

// ---------- répartition ----------

@Composable
private fun CarteRepartition(rep: JSONObject, choisie: String, onChoix: (String) -> Unit) {
    val dispo = DIMENSIONS.filter { rep.optJSONArray(it.first)?.length() ?: 0 > 0 }
    if (dispo.isEmpty()) return
    val dim = if (dispo.any { it.first == choisie }) choisie else dispo.first().first
    val parts = rep.optJSONArray(dim).let { a -> (0 until (a?.length() ?: 0)).mapNotNull { a?.optJSONObject(it) } }
    Carte {
        CarteEntete("Répartition")
        if (dispo.size > 1) Segmente(dispo, dim, onChoix, remplir = true)
        BarreRepartition(parts.mapIndexed { i, p -> (p.num("poids") ?: 0.0) to Pt.serie(i) })
        Column(verticalArrangement = Arrangement.spacedBy(11.dp)) {
            parts.forEachIndexed { i, p ->
                LigneRepartition(Pt.serie(i), p.str("nom") ?: "—", euros(p.num("valeur"), cents = false), pct(p.num("poids"), sign = false))
            }
        }
    }
}

// ---------- dividendes ----------

@Composable
private fun CarteDividendes(d: JSONObject, prochain: String?) {
    val total = d.num("total") ?: 0.0
    val mois = d.list("par_mois")
    Carte {
        CarteEntete("Dividendes", "12 derniers mois")
        GrilleIndicateurs(
            listOf(
                Indicateur("Reçus", euros(total, cents = false), if (total > 0) euros(total / 12, cents = false) + " par mois" else null),
                Indicateur(
                    "Rendement", pct(d.num("rendement_valeur"), sign = false, digits = 2),
                    d.num("rendement_achat")?.let { pct(it, sign = false, digits = 2) + " sur prix d'achat" },
                ),
            ),
        )
        if (total > 0 && mois.isNotEmpty()) BarresMensuelles(mois)
        else Text("Aucun dividende reçu sur la période.", fontSize = 13.sp, color = Pt.Mute)
        if (prochain != null) Paire("Prochain versement", prochain, Pt.Encre)
    }
}

@Composable
private fun BarresMensuelles(mois: List<JSONObject>) {
    val valeurs = mois.map { it.num("montant") ?: 0.0 }
    val maxi = valeurs.max().takeIf { it > 0 } ?: 1.0
    Row(Modifier.fillMaxWidth().height(90.dp), horizontalArrangement = Arrangement.SpaceBetween) {
        mois.forEachIndexed { i, m ->
            val v = valeurs[i]
            Column(Modifier.width(18.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                Box(Modifier.weight(1f).fillMaxWidth(), contentAlignment = Alignment.BottomCenter) {
                    Box(
                        Modifier.fillMaxWidth().height(max(2.0, v / maxi * 62).dp)
                            .clip(RoundedCornerShape(4.dp)).background(if (v > 0) Pt.Accent else Pt.Ligne),
                    )
                }
                Text(LETTRES_MOIS[((m.str("mois")?.takeLast(2)?.toIntOrNull() ?: 1) - 1).coerceIn(0, 11)],
                    Modifier.padding(top = 6.dp), fontSize = 10.sp, color = Pt.Mute, maxLines = 1)
            }
        }
    }
}

// ---------- ventes réalisées (reprise de l'ancien écran) ----------

@Composable
private fun VentesRealisees() {
    var ouvert by remember { mutableStateOf(false) }
    Carte(onClick = { ouvert = !ouvert }) {
        CarteEntete("Ventes réalisées")
        if (!ouvert) {
            Muted("Toucher pour afficher")
        } else {
            Loaded(rememberCall("ventes_realisees")) { data ->
                val ventes = data.list("ventes")
                if (ventes.isEmpty()) Muted("Aucune vente enregistrée.")
                Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    for (v in ventes) {
                        val gain = v.num("gain")
                        InfoRow(
                            v.str("name") ?: v.str("isin") ?: "—",
                            if (gain == null) "—" else euros(gain, sign = true),
                            tone = gain,
                            sub = day(v.str("date")),
                        )
                    }
                }
            }
        }
    }
}
