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
import androidx.compose.material.icons.filled.Settings
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
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.navigation.NavController
import fr.julesgourio.patrimoine.ui.Routes
import fr.julesgourio.patrimoine.ui.components.CallScreen
import fr.julesgourio.patrimoine.ui.components.Carte
import fr.julesgourio.patrimoine.ui.components.CarteEntete
import fr.julesgourio.patrimoine.ui.components.GraphiqueBourse
import fr.julesgourio.patrimoine.ui.components.GrilleIndicateurs
import fr.julesgourio.patrimoine.ui.components.Indicateur
import fr.julesgourio.patrimoine.ui.components.LocalSync
import fr.julesgourio.patrimoine.ui.components.ModeleBourse
import fr.julesgourio.patrimoine.ui.components.PastilleVariation
import fr.julesgourio.patrimoine.ui.components.SectionCard
import fr.julesgourio.patrimoine.ui.components.SelecteurPeriode
import fr.julesgourio.patrimoine.ui.components.dateCourte
import fr.julesgourio.patrimoine.ui.components.day
import fr.julesgourio.patrimoine.ui.components.euros
import fr.julesgourio.patrimoine.ui.components.initiales
import fr.julesgourio.patrimoine.ui.components.int
import fr.julesgourio.patrimoine.ui.components.list
import fr.julesgourio.patrimoine.ui.components.moment
import fr.julesgourio.patrimoine.ui.components.num
import fr.julesgourio.patrimoine.ui.components.number
import fr.julesgourio.patrimoine.ui.components.objOrNull
import fr.julesgourio.patrimoine.ui.components.pct
import fr.julesgourio.patrimoine.ui.components.rememberCall
import fr.julesgourio.patrimoine.ui.components.str
import fr.julesgourio.patrimoine.ui.components.strings
import fr.julesgourio.patrimoine.ui.theme.LocalMoney
import fr.julesgourio.patrimoine.ui.theme.Pt
import org.json.JSONArray
import org.json.JSONObject
import kotlin.math.max
import kotlin.math.min

/** Écran Patrimoine (onglet d'accueil, maquette docs/maquette) : tout vient de l'outil `accueil_ecran`, un seul appel. */

private val PERIODES = listOf("1S", "1M", "3M", "YTD", "1A", "MAX")
private val LEGENDE_PERIODE = mapOf(
    "1S" to "7 jours", "1M" to "1 mois", "3M" to "3 mois", "YTD" to "depuis le 1er janv.", "1A" to "1 an", "MAX" to "depuis l'origine",
)
private val DEBUT_CASCADE = mapOf(
    "1S" to "Il y a 1 semaine", "1M" to "Il y a 1 mois", "3M" to "Il y a 3 mois", "YTD" to "Au 1er janvier", "1A" to "Il y a 1 an",
)
private val COULEUR_TYPE = mapOf("placements" to Pt.Series[0], "courants" to Pt.Series[5], "livrets" to Pt.Series[2])
private val VIGNETTES_PLACEMENTS = listOf(Color(0xFF2A78D6), Color(0xFFEB6834), Color(0xFF1BAF7A), Color(0xFF6250D6))
private val VIGNETTE_COURANT = Color(0xFF5A6272)
private val VIGNETTE_LIVRET = Color(0xFF0E8A8A)

private fun serie(a: JSONArray?): Pair<List<String>, List<Double>> {
    if (a == null) return emptyList<String>() to emptyList()
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

@Composable
private fun Marge(content: @Composable () -> Unit) = Box(Modifier.padding(horizontal = 16.dp)) { content() }

@Composable
fun AccueilScreen(nav: NavController) {
    val sync = LocalSync.current
    val state = rememberCall("accueil_ecran")
    var periode by rememberSaveable { mutableStateOf("1A") }

    CallScreen(state, PaddingValues(0.dp), horizontal = 0.dp) { data ->
        item { EnTete(onReglages = { nav.navigate(Routes.REGLAGES) }, onAjouter = { nav.navigate(Routes.AJOUTER) }) }
        val total = data.num("total")
        if (data.str("erreur") != null || total == null) {
            item { Marge { Bienvenue(onSettings = { nav.navigate(Routes.REGLAGES) }, onSync = sync.start) } }
            return@CallScreen
        }
        val periodes = data.objOrNull("periodes")
        val choix = if (periodes?.has(periode) == true) periode else "1A"
        val p = periodes?.objOrNull(choix)
        item { Marge { BlocPrincipal(data, p, choix, total) { periode = it } } }
        p?.objOrNull("cascade")?.let { c -> item { Marge { CarteVariation(c, p, choix) } } }
        if (data.list("types").isNotEmpty()) item { Marge { CarteRepartition(data) } }
        data.objOrNull("indicateurs")?.let { i -> item { Marge { CarteIndicateurs(i) } } }
        item { Marge { CarteComptes(data, nav) } }
        data.objOrNull("derniere_analyse")?.let { a -> item { Marge { CarteAnalyse(a, nav) } } }
        item { Marge { CarteSuite(data, nav) } }
    }
}

// ---------- en-tête ----------

@Composable
private fun EnTete(onReglages: () -> Unit, onAjouter: () -> Unit) {
    Row(
        Modifier.fillMaxWidth().windowInsetsPadding(WindowInsets.statusBars).padding(horizontal = 16.dp).height(44.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text("Patrimoine", Modifier.weight(1f), fontSize = 26.sp, fontWeight = FontWeight.Bold, letterSpacing = (-0.5).sp, color = Pt.Encre)
        Box(Modifier.size(40.dp).clip(CircleShape).background(Pt.Carte).clickable(onClick = onReglages), contentAlignment = Alignment.Center) {
            Icon(Icons.Filled.Settings, contentDescription = "Réglages", Modifier.size(20.dp), tint = Pt.Encre)
        }
        Box(Modifier.padding(start = 6.dp).size(40.dp).clip(CircleShape).background(Pt.Encre).clickable(onClick = onAjouter), contentAlignment = Alignment.Center) {
            Icon(Icons.Filled.Add, contentDescription = "Ajouter un compte", Modifier.size(20.dp), tint = Color.White)
        }
    }
}

// ---------- bloc sombre ----------

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun BlocPrincipal(data: JSONObject, p: JSONObject?, periode: String, total: Double, onPeriode: (String) -> Unit) {
    val money = LocalMoney.current
    val variation = p?.num("variation")
    val variationPct = p?.num("variation_pct")
    val ton = if ((variation ?: 0.0) < 0) money.lossNight else money.gainNight
    val types = data.list("types")
    val modele = remember(data, periode) {
        val serie = serie(p?.optJSONArray("serie"))
        val piles = types.mapNotNull { t ->
            val id = t.str("id") ?: return@mapNotNull null
            val v = serie(p?.objOrNull("types")?.optJSONArray(id)).second
            if (v.size == serie.first.size) (COULEUR_TYPE[id] ?: Pt.Series[5]) to v else null
        }
        if (serie.first.size < 2 || piles.isEmpty()) null else ModeleBourse.Comptes(serie.first, piles, periode in listOf("1A", "MAX"))
    }
    Column(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(24.dp)).background(Pt.Nuit).padding(top = 18.dp, bottom = 12.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Column(Modifier.fillMaxWidth().padding(horizontal = 18.dp)) {
            val n = data.int("nb_comptes") ?: 0
            Text("$n compte${if (n > 1) "s" else ""} · net", fontSize = 12.sp, fontWeight = FontWeight.Medium, color = Pt.NuitSub)
            Text(euros(total, cents = false), fontSize = 38.sp, fontWeight = FontWeight.Bold, letterSpacing = (-1.1).sp,
                color = Color.White, maxLines = 1, lineHeight = 42.sp)
        }
        FlowRow(
            Modifier.fillMaxWidth().padding(horizontal = 18.dp).offset(y = (-6).dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(4.dp),
            itemVerticalAlignment = Alignment.CenterVertically,
        ) {
            PastilleVariation(variationPct, sombre = true)
            if (variation != null) Text(euros(variation, sign = true, cents = false), fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = ton)
            val depuis = if (p != null && !p.optBoolean("complet", true)) "depuis le " + dateCourte(p.str("depuis"), true) else LEGENDE_PERIODE[periode].orEmpty()
            Text("$depuis · versements inclus", fontSize = 13.sp, fontWeight = FontWeight.Medium, color = Pt.NuitSub)
        }
        if (modele != null) {
            GraphiqueBourse(modele)
            FlowRow(
                Modifier.fillMaxWidth().padding(horizontal = 18.dp),
                horizontalArrangement = Arrangement.spacedBy(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                types.forEach { t ->
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
                        Box(Modifier.size(10.dp, 8.dp).clip(RoundedCornerShape(2.dp)).background(COULEUR_TYPE[t.str("id")] ?: Pt.Series[5]))
                        Text(t.str("nom") ?: "—", fontSize = 12.sp, color = Pt.NuitSub, maxLines = 1)
                    }
                }
            }
        } else {
            Box(Modifier.fillMaxWidth().height(96.dp).padding(horizontal = 18.dp), contentAlignment = Alignment.Center) {
                Text("Pas assez d'historique", fontSize = 12.sp, color = Pt.NuitSub)
            }
        }
        SelecteurPeriode(PERIODES, periode, onPeriode)
    }
}

// ---------- d'où vient la variation ----------

@Composable
private fun CarteVariation(c: JSONObject, p: JSONObject, periode: String) {
    val debut = c.num("debut") ?: return
    val fin = c.num("fin") ?: return
    val libDebut = if (!p.optBoolean("complet", true) || periode == "MAX") "Au début · " + dateCourte(p.str("depuis"), true)
    else DEBUT_CASCADE[periode] ?: "Au début"
    // (libellé, valeur, total ?) ; les étapes sont des écarts posés les uns sur les autres.
    val lignes = listOf(
        Triple(libDebut, debut, true),
        Triple("Épargne", c.num("epargne") ?: 0.0, false),
        Triple("Variation des marchés", c.num("marches") ?: 0.0, false),
        Triple("Dividendes et intérêts", c.num("dividendes") ?: 0.0, false),
        Triple("Aujourd'hui", fin, true),
    )
    val bornes = ArrayList<Double>()
    var cumul = debut
    bornes += debut
    lignes.filter { !it.third }.forEach { cumul += it.second; bornes += cumul }
    bornes += fin
    val mn = bornes.min()
    val mx = bornes.max()
    val etendue = (mx - mn).takeIf { it > 0 } ?: 1.0
    val bas = max(0.0, mn - 0.25 * etendue)
    val haut = mx + 0.1 * etendue
    val money = LocalMoney.current
    Carte {
        CarteEntete("D'où vient la variation", LEGENDE_PERIODE[periode])
        Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
            var run = debut
            lignes.forEach { (titre, v, total) ->
                val a: Double
                val b: Double
                if (total) { a = bas; b = v; run = v } else { a = run; b = run + v; run += v }
                val couleur = if (total) Pt.Encre else if (v < 0) money.loss else money.gain
                Row(Modifier.fillMaxWidth().height(32.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(titre, Modifier.width(122.dp), fontSize = 12.sp, fontWeight = if (total) FontWeight.SemiBold else FontWeight.Medium,
                        color = if (total) Pt.Encre else Pt.Sub, maxLines = 2, lineHeight = 15.sp, overflow = TextOverflow.Ellipsis)
                    Box(
                        Modifier.weight(1f).height(14.dp).drawBehind {
                            val x1 = ((min(a, b) - bas) / (haut - bas)).toFloat() * size.width
                            val x2 = ((max(a, b) - bas) / (haut - bas)).toFloat() * size.width
                            val w = max(x2 - x1, 2.dp.toPx())
                            drawRoundRect(couleur, Offset(x1.coerceIn(0f, size.width - w), 0f), Size(w, size.height), CornerRadius(3.dp.toPx()))
                        },
                    )
                    Text(if (total) euros(v, cents = false) else euros(v, sign = true, cents = false), Modifier.width(76.dp), textAlign = TextAlign.End,
                        fontSize = 13.sp, fontWeight = FontWeight.SemiBold, color = couleur, maxLines = 1, softWrap = false)
                }
            }
        }
    }
}

// ---------- répartition ----------

@Composable
private fun CarteRepartition(data: JSONObject) {
    val types = data.list("types")
    val investi = types.firstOrNull { it.str("id") == "placements" }?.num("part")
    Carte {
        CarteEntete("Répartition")
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(16.dp)) {
            Box(Modifier.size(120.dp), contentAlignment = Alignment.Center) {
                Canvas(Modifier.size(120.dp)) {
                    val trait = 16.dp.toPx()
                    val d = size.width - trait
                    val ecart = if (types.size > 1) 2.5f else 0f
                    var debut = -90f
                    types.forEach { t ->
                        val f = (t.num("part") ?: 0.0).toFloat().coerceAtLeast(0f)
                        val sweep = f * 360f
                        drawArc(COULEUR_TYPE[t.str("id")] ?: Pt.Series[5], debut, max(sweep - ecart, 0.5f), false,
                            Offset(trait / 2, trait / 2), Size(d, d), style = Stroke(trait))
                        debut += sweep
                    }
                }
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text("Investi", fontSize = 11.sp, color = Pt.Mute)
                    Text(pct(investi, sign = false, digits = 0), fontSize = 17.sp, fontWeight = FontWeight.Bold, color = Pt.Encre)
                }
            }
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(11.dp)) {
                types.forEach { t ->
                    Row(verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Box(Modifier.padding(top = 5.dp).size(8.dp).clip(RoundedCornerShape(3.dp)).background(COULEUR_TYPE[t.str("id")] ?: Pt.Series[5]))
                        Column(Modifier.weight(1f)) {
                            Text(t.str("nom") ?: "—", fontSize = 13.sp, fontWeight = FontWeight.Medium, color = Pt.Encre, maxLines = 1, overflow = TextOverflow.Ellipsis)
                            Text(euros(t.num("valeur"), cents = false), fontSize = 12.sp, color = Pt.Mute, maxLines = 1)
                        }
                        Text(pct(t.num("part"), sign = false, digits = 0), fontSize = 13.sp, fontWeight = FontWeight.SemiBold, color = Pt.Encre, maxLines = 1)
                    }
                }
            }
        }
    }
}

// ---------- indicateurs ----------

@Composable
private fun CarteIndicateurs(i: JSONObject) {
    Carte {
        CarteEntete("Indicateurs")
        GrilleIndicateurs(
            listOf(
                Indicateur("Taux d'épargne", pct(i.num("taux_epargne"), sign = false, digits = 0), "moyenne sur 12 mois"),
                Indicateur("Épargne de précaution", i.num("mois_precaution")?.let { number(it, 1) + " mois" } ?: "—",
                    "de dépenses disponibles"),
                Indicateur("Disponible sous 48 h", euros(i.num("disponible_48h"), cents = false),
                    i.num("disponible_part")?.let { pct(it, sign = false, digits = 0) + " du patrimoine" }),
                Indicateur("PEA", i.str("pea_ouverture")?.let { if (i.optBoolean("pea_5_ans")) "5 ans atteints" else "5 ans le " + dateCourte(i.str("pea_5_ans_date"), true) } ?: "—",
                    i.str("pea_ouverture")?.let { "ouvert le " + dateCourte(it, true) }),
                Indicateur("Après impôts latents", euros(i.num("apres_impots"), cents = false), "si tout était vendu"),
            ),
        )
    }
}

// ---------- comptes ----------

@Composable
private fun CarteComptes(data: JSONObject, nav: NavController) {
    val comptes = data.list("comptes")
    Carte {
        CarteEntete("Comptes", "30 jours")
        Column {
            var placements = 0
            comptes.forEachIndexed { i, c ->
                val type = c.str("type")
                val couleur = when (type) {
                    "placements" -> VIGNETTES_PLACEMENTS[placements++ % VIGNETTES_PLACEMENTS.size]
                    "livrets" -> VIGNETTE_LIVRET
                    else -> VIGNETTE_COURANT
                }
                LigneCompte(c, couleur, separateur = i > 0, onClick = if (c.optBoolean("titres")) ({ nav.navigate(Routes.BOURSE) }) else null)
            }
        }
    }
}

@Composable
private fun LigneCompte(c: JSONObject, couleur: Color, separateur: Boolean, onClick: (() -> Unit)?) {
    val money = LocalMoney.current
    val pc = c.num("var_30j_pct")
    val stable = pc != null && kotlin.math.abs(pc) < 0.0005
    val trait = if (pc == null || stable) Pt.Mute.copy(alpha = 0.6f) else if (pc > 0) money.gain else money.loss
    val valeurs = c.optJSONArray("serie_30j")?.let { a -> (0 until a.length()).mapNotNull { a.optDouble(it).takeIf { v -> !v.isNaN() } } }.orEmpty()
    Column(Modifier.fillMaxWidth().let { if (onClick != null) it.clickable(onClick = onClick) else it }) {
        if (separateur) Box(Modifier.fillMaxWidth().height(1.dp).background(Pt.Ligne))
        Row(Modifier.fillMaxWidth().padding(vertical = 9.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Box(Modifier.size(36.dp).clip(RoundedCornerShape(11.dp)).background(couleur), contentAlignment = Alignment.Center) {
                Text(initiales(c.str("nom")), fontSize = 12.sp, fontWeight = FontWeight.Bold, color = Color.White, maxLines = 1)
            }
            Column(Modifier.weight(1f)) {
                Text(c.str("nom") ?: "—", fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = Pt.Encre, maxLines = 1, overflow = TextOverflow.Ellipsis)
                Text(c.str("type_nom") ?: "", fontSize = 12.sp, color = Pt.Mute, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
            Courbette(valeurs, trait, stable)
            Column(horizontalAlignment = Alignment.End) {
                Text(euros(c.num("valeur"), cents = false), fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = Pt.Encre, maxLines = 1)
                if (c.num("var_30j") != null) Text(if (stable) "stable" else if (pc == null) euros(c.num("var_30j"), sign = true, cents = false) else pct(pc, digits = 1),
                    fontSize = 12.sp, fontWeight = FontWeight.SemiBold, maxLines = 1, color = if (stable || pc == null) Pt.Mute else trait)
            }
        }
    }
}

/** Petite courbe de 54 × 24 : plate au milieu quand le compte n'a pas bougé. */
@Composable
private fun Courbette(valeurs: List<Double>, couleur: Color, plate: Boolean) {
    Canvas(Modifier.size(54.dp, 24.dp)) {
        if (valeurs.size < 2) return@Canvas
        val lo = valeurs.min()
        val hi = valeurs.max()
        val chemin = Path()
        valeurs.forEachIndexed { i, v ->
            val x = 1.dp.toPx() + i * (size.width - 2.dp.toPx()) / (valeurs.size - 1)
            val y = if (plate || hi == lo) size.height / 2 else size.height - 2.dp.toPx() - ((v - lo) / (hi - lo)).toFloat() * (size.height - 4.dp.toPx())
            if (i == 0) chemin.moveTo(x, y) else chemin.lineTo(x, y)
        }
        drawPath(chemin, couleur, style = Stroke(1.6.dp.toPx(), cap = StrokeCap.Round, join = StrokeJoin.Round))
    }
}

// ---------- analyse, à regarder, synchronisation ----------

@Composable
private fun CarteAnalyse(a: JSONObject, nav: NavController) {
    Carte(onClick = { a.int("id")?.let { nav.navigate(Routes.analyse(it)) } }) {
        CarteEntete("Dernière analyse", "séance du " + day(a.str("seance")))
        Text(a.str("titre") ?: "Analyse", fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = Pt.Encre)
        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
            a.strings("points_cles").forEach { Text("• $it", fontSize = 13.sp, color = Pt.Sub, lineHeight = 18.sp) }
        }
    }
}

@Composable
private fun CarteSuite(data: JSONObject, nav: NavController) {
    val sync = LocalSync.current
    val ordres = data.int("ordres_proposes") ?: 0
    val alertes = data.int("alertes_30j") ?: 0
    val derniere = data.objOrNull("derniere_synchro")
    Carte {
        CarteEntete("À regarder")
        Column {
            var premiere = true
            if (ordres > 0) {
                LigneLien("Ordres préparés", "À passer toi-même dans Trade Republic", "$ordres", !premiere) { nav.navigate(Routes.ORDRES) }
                premiere = false
            }
            if (alertes > 0) {
                LigneLien("Alertes", "30 derniers jours", "$alertes", !premiere) { nav.navigate(Routes.ALERTES) }
                premiere = false
            }
            LigneLien("Plus", "Analyses, opérations, vendeurs, réglages", null, !premiere) { nav.navigate(Routes.PLUS) }
        }
        Box(Modifier.fillMaxWidth().height(1.dp).background(Pt.Ligne))
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Column(Modifier.weight(1f)) {
                Text("Dernière synchronisation", fontSize = 13.sp, fontWeight = FontWeight.Medium, color = Pt.Encre)
                Text(moment(derniere?.str("at")), fontSize = 12.sp, color = Pt.Mute)
            }
            Box(
                Modifier.height(36.dp).clip(RoundedCornerShape(18.dp)).background(if (sync.running) Pt.Pastille else Pt.Encre)
                    .clickable(enabled = !sync.running, onClick = sync.start).padding(horizontal = 14.dp),
                contentAlignment = Alignment.Center,
            ) {
                Text(if (sync.running) "En cours…" else "Synchroniser", fontSize = 13.sp, fontWeight = FontWeight.SemiBold,
                    color = if (sync.running) Pt.Sub else Color.White)
            }
        }
        sync.lastError?.let { Text(it, fontSize = 12.sp, color = Pt.Baisse) }
        val lignes = sync.lastLines?.lines() ?: derniere?.optJSONArray("summary")?.let { a -> (0 until a.length()).map { a.optString(it) } } ?: emptyList()
        lignes.filter { it.isNotBlank() }.forEach { Text(it, fontSize = 12.sp, color = Pt.Mute) }
    }
}

@Composable
private fun LigneLien(titre: String, sous: String, valeur: String?, separateur: Boolean, onClick: () -> Unit) {
    Column(Modifier.fillMaxWidth().clickable(onClick = onClick)) {
        if (separateur) Box(Modifier.fillMaxWidth().height(1.dp).background(Pt.Ligne))
        Row(Modifier.fillMaxWidth().padding(vertical = 10.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Column(Modifier.weight(1f)) {
                Text(titre, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = Pt.Encre)
                Text(sous, fontSize = 12.sp, color = Pt.Mute, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
            Text(valeur ?: "›", fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = if (valeur != null) Pt.Encre else Pt.Mute)
        }
    }
}

@Composable
private fun Bienvenue(onSettings: () -> Unit, onSync: () -> Unit) {
    SectionCard("Bienvenue") {
        Text("La base du téléphone est encore vide.")
        Text("Le plus simple : copie le fichier data/patrimoine.db du PC sur le téléphone, puis Réglages → " +
            "« Importer une base ». Tout l'historique (CMB depuis 2016, PEG, analyses) arrive d'un coup.")
        Text("Sinon : renseigne Trade Republic et la CMB dans les Réglages, puis synchronise.")
        androidx.compose.material3.Button(onClick = onSettings) { Text("Ouvrir les réglages") }
        androidx.compose.material3.Button(onClick = onSync) { Text("Synchroniser") }
    }
}
