package fr.julesgourio.patrimoine.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import fr.julesgourio.patrimoine.ui.theme.LocalMoney
import fr.julesgourio.patrimoine.ui.theme.Pt

// Composants de la maquette (docs/maquette), partagés par les écrans refaits.

/** Carte blanche, rayon 20. */
@Composable
fun Carte(modifier: Modifier = Modifier, onClick: (() -> Unit)? = null, content: @Composable ColumnScope.() -> Unit) {
    Column(
        modifier.fillMaxWidth().clip(RoundedCornerShape(20.dp)).background(Pt.Carte)
            .let { if (onClick != null) it.clickable(onClick = onClick) else it }
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
        content = content,
    )
}

/** Titre de carte à gauche, mention discrète (ou action) à droite. */
@Composable
fun CarteEntete(titre: String, mention: String? = null, droite: (@Composable () -> Unit)? = null) {
    Row(Modifier.fillMaxWidth().heightIn(min = 28.dp), verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(titre, Modifier.weight(1f), fontSize = 15.sp, fontWeight = FontWeight.SemiBold, color = Pt.Encre,
            maxLines = 1, overflow = TextOverflow.Ellipsis)
        if (mention != null) Text(mention, fontSize = 12.sp, fontWeight = FontWeight.Medium, color = Pt.Mute, maxLines = 1)
        droite?.invoke()
    }
}

class Indicateur(val libelle: String, val valeur: String, val sous: String? = null, val ton: Double? = null, val ton2: Color? = null)

/** Indicateurs sur deux colonnes, séparés par des filets fins. */
@Composable
fun GrilleIndicateurs(items: List<Indicateur>) {
    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(Pt.Ligne), verticalArrangement = Arrangement.spacedBy(1.dp)) {
        items.chunked(2).forEach { ligne ->
            Row(Modifier.fillMaxWidth().height(IntrinsicSize.Min), horizontalArrangement = Arrangement.spacedBy(1.dp)) {
                ligne.forEachIndexed { i, it ->
                    val tone = it.ton2 ?: if (it.ton != null) gainColor(it.ton) else Pt.Encre
                    Column(
                        Modifier.weight(1f).fillMaxHeight().background(Pt.Carte)
                            .padding(start = if (i == 1) 14.dp else 0.dp, top = 12.dp, bottom = 12.dp, end = if (i == 1) 0.dp else 12.dp),
                        verticalArrangement = Arrangement.spacedBy(3.dp),
                    ) {
                        Text(it.libelle, fontSize = 12.sp, fontWeight = FontWeight.Medium, color = Pt.Mute)
                        Text(it.valeur, fontSize = 17.sp, fontWeight = FontWeight.SemiBold, color = tone, maxLines = 1)
                        if (it.sous != null) Text(it.sous, fontSize = 12.sp, fontWeight = FontWeight.Medium, color = Pt.Mute, lineHeight = 16.sp)
                    }
                }
                if (ligne.size == 1) Box(Modifier.weight(1f).fillMaxHeight().background(Pt.Carte))
            }
        }
    }
}

/** Pastille de variation (▲ +0,20 %), sur fond sombre ou clair ; neutre sans valeur. */
@Composable
fun PastilleVariation(valeur: Double?, sombre: Boolean = false) {
    val money = LocalMoney.current
    val up = (valeur ?: 0.0) >= 0
    val fg = if (valeur == null) (if (sombre) Pt.NuitSub else Pt.Mute) else if (sombre) (if (up) money.gainNight else money.lossNight) else (if (up) money.gain else money.loss)
    val bg = when {
        valeur == null -> if (sombre) Pt.Nuit2 else Pt.Pastille
        sombre -> fg.copy(alpha = 0.14f)
        up -> Pt.HausseFond
        else -> Pt.BaisseFond
    }
    Row(Modifier.height(24.dp).clip(RoundedCornerShape(8.dp)).background(bg).padding(horizontal = 8.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        if (valeur != null) Text(if (up) "▲" else "▼", fontSize = 9.sp, color = fg)
        Text(if (valeur == null) "—" else pct(valeur, digits = 2), fontSize = 13.sp, fontWeight = FontWeight.SemiBold, color = fg, maxLines = 1)
    }
}

/**
 * Sélecteur segmenté : [options] = (clé, libellé). [sombre] pour le bloc sombre, [remplir] pour occuper toute la
 * largeur (chaque segment à égalité).
 */
@Composable
fun Segmente(
    options: List<Pair<String, String>>,
    choix: String,
    onChoix: (String) -> Unit,
    sombre: Boolean = false,
    remplir: Boolean = false,
    modifier: Modifier = Modifier,
) {
    Row(
        modifier.let { if (remplir) it.fillMaxWidth() else it }.clip(RoundedCornerShape(10.dp))
            .background(if (sombre) Pt.Nuit2 else Pt.Pastille).padding(3.dp),
        horizontalArrangement = Arrangement.spacedBy(2.dp),
    ) {
        options.forEach { (cle, libelle) ->
            val on = cle == choix
            Box(
                Modifier.let { if (remplir) it.weight(1f) else it.widthIn(min = 34.dp) }.height(28.dp)
                    .clip(RoundedCornerShape(8.dp)).background(if (on) Color.White else Color.Transparent)
                    .clickable(role = Role.Tab) { onChoix(cle) }.padding(horizontal = 9.dp),
                contentAlignment = Alignment.Center,
            ) {
                Text(libelle, fontSize = 12.sp, fontWeight = FontWeight.SemiBold, maxLines = 1, textAlign = TextAlign.Center,
                    color = if (on) Pt.Encre else if (sombre) Pt.NuitSub else Pt.Sub)
            }
        }
    }
}

/** Sélecteur de période du bloc sombre : cases égales, la choisie en relief. */
@Composable
fun SelecteurPeriode(periodes: List<String>, choix: String, onChoix: (String) -> Unit) {
    Row(Modifier.fillMaxWidth().padding(horizontal = 12.dp), horizontalArrangement = Arrangement.spacedBy(2.dp)) {
        periodes.forEach { p ->
            val on = p == choix
            Box(
                Modifier.weight(1f).height(34.dp).clip(RoundedCornerShape(10.dp)).background(if (on) Pt.Nuit2 else Color.Transparent)
                    .clickable(role = Role.Tab) { onChoix(p) },
                contentAlignment = Alignment.Center,
            ) {
                Text(p, fontSize = 12.sp, fontWeight = FontWeight.SemiBold, color = if (on) Color.White else Pt.NuitSub, maxLines = 1)
            }
        }
    }
}

class Filtre(val id: String, val libelle: String, val couleur: Color? = null)

/** Pastilles de filtre qui défilent ; [margeLaterale] aligne la première sur la marge de l'écran. */
@Composable
fun PastillesFiltre(filtres: List<Filtre>, choix: String, onChoix: (String) -> Unit, margeLaterale: Dp = 16.dp) {
    Row(
        Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).padding(horizontal = margeLaterale),
        horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        filtres.forEach { f ->
            val on = f.id == choix
            Row(
                Modifier.height(36.dp).clip(RoundedCornerShape(18.dp)).background(if (on) Pt.Encre else Pt.Carte)
                    .clickable(role = Role.Tab) { onChoix(f.id) }.padding(horizontal = 13.dp),
                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(7.dp),
            ) {
                if (f.couleur != null) Box(Modifier.size(8.dp).clip(CircleShape).background(f.couleur))
                Text(f.libelle, fontSize = 13.sp, fontWeight = FontWeight.SemiBold, color = if (on) Color.White else Pt.Sub, maxLines = 1)
            }
        }
    }
}

/** Ligne de liste : vignette à initiales, titre et sous-titre, deux lignes de valeur à droite. */
@Composable
fun LigneListe(
    initiales: String,
    couleur: Color,
    titre: String,
    sous: String?,
    droite: String,
    droiteSous: String? = null,
    tonDroite: Double? = null,
    separateur: Boolean = true,
    onClick: (() -> Unit)? = null,
) {
    Column(Modifier.fillMaxWidth().let { if (onClick != null) it.clickable(onClick = onClick) else it }) {
        if (separateur) Box(Modifier.fillMaxWidth().height(1.dp).background(Pt.Ligne))
        Row(Modifier.fillMaxWidth().padding(vertical = 9.dp), verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Box(Modifier.size(36.dp).clip(RoundedCornerShape(11.dp)).background(couleur), contentAlignment = Alignment.Center) {
                Text(initiales, fontSize = 12.sp, fontWeight = FontWeight.Bold, color = Color.White, maxLines = 1)
            }
            Column(Modifier.weight(1f)) {
                Text(titre, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = Pt.Encre, maxLines = 1, overflow = TextOverflow.Ellipsis)
                if (sous != null) Text(sous, fontSize = 12.sp, color = Pt.Mute, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
            Column(horizontalAlignment = Alignment.End) {
                Text(droite, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = Pt.Encre, maxLines = 1)
                if (droiteSous != null) Text(droiteSous, fontSize = 12.sp, fontWeight = FontWeight.SemiBold, maxLines = 1,
                    color = if (tonDroite != null) gainColor(tonDroite) else Pt.Mute)
            }
        }
    }
}

/** Barre segmentée : chaque part proportionnelle à son poids, une couleur chacune. */
@Composable
fun BarreRepartition(parts: List<Pair<Double, Color>>) {
    Row(Modifier.fillMaxWidth().height(12.dp).clip(RoundedCornerShape(6.dp)), horizontalArrangement = Arrangement.spacedBy(2.dp)) {
        parts.filter { it.first > 0 }.forEach { (poids, couleur) ->
            Box(Modifier.weight(poids.toFloat()).fillMaxHeight().background(couleur))
        }
    }
}

/** Ligne de légende de répartition : pastille, libellé, montant discret et pourcentage. */
@Composable
fun LigneRepartition(couleur: Color, libelle: String, montant: String, part: String) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Box(Modifier.size(8.dp).clip(RoundedCornerShape(3.dp)).background(couleur))
        Text(libelle, Modifier.weight(1f), fontSize = 13.sp, fontWeight = FontWeight.Medium, color = Pt.Encre, maxLines = 1, overflow = TextOverflow.Ellipsis)
        Text(montant, fontSize = 13.sp, fontWeight = FontWeight.Medium, color = Pt.Mute, maxLines = 1)
        Text(part, Modifier.widthIn(min = 52.dp), fontSize = 13.sp, fontWeight = FontWeight.SemiBold, color = Pt.Encre, maxLines = 1, textAlign = TextAlign.End)
    }
}
