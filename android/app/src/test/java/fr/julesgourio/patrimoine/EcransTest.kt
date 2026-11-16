package fr.julesgourio.patrimoine

import androidx.compose.ui.test.hasScrollToIndexAction
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.down
import androidx.compose.ui.test.performTouchInput
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performScrollToIndex
import androidx.compose.ui.test.onRoot
import androidx.navigation.NavHostController
import androidx.navigation.compose.rememberNavController
import com.github.takahirom.roborazzi.captureRoboImage
import fr.julesgourio.patrimoine.engine.Engine
import fr.julesgourio.patrimoine.engine.Reply
import fr.julesgourio.patrimoine.ui.AppContent
import fr.julesgourio.patrimoine.ui.Routes
import fr.julesgourio.patrimoine.ui.components.SyncControl
import fr.julesgourio.patrimoine.ui.theme.PatrimoineTheme
import org.json.JSONObject
import org.junit.After
import org.junit.Assume.assumeTrue
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import java.io.File

/**
 * Photographie chaque écran de l'appli, rendu par le vrai code Compose sur un téléphone de la taille d'un Pixel 8a,
 * avec les réponses du moteur lues dans PATRIMOINE_ECRANS (voir `scripts/ecrans_json.py`). Sans ce dossier, le test
 * est ignoré. Les PNG vont dans PATRIMOINE_CAPTURES (défaut : build/captures).
 */
@RunWith(RobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [35], qualifiers = "w411dp-h914dp-420dpi", application = android.app.Application::class)
class EcransTest {
    companion object {
        const val ACTION = "DE000DEMO001"
        const val ETF = "IE000DEMO005"
        // Hauteur (fraction de l'écran) du graphique tactile de chaque écran, pour poser le doigt dessus
        const val GY_ACCUEIL = 0.4f
        const val GY_FLUX = 0.3f
        const val GY_BOURSE = 0.4f
        const val GY_TITRE = 0.4f
        const val SANS_COUT = "NL0000235190"  // PEG du jeu fictif : cours connus, prix de revient inconnu
    }

    @get:Rule
    val rule = createComposeRule()

    private val ecrans = System.getenv("PATRIMOINE_ECRANS")?.takeIf { it.isNotBlank() }?.let(::File)
    private val sortie = File(System.getenv("PATRIMOINE_CAPTURES") ?: "build/captures")

    @Before
    fun fixtures() {
        assumeTrue("PATRIMOINE_ECRANS non défini : pas de captures", ecrans?.isDirectory == true)
        Engine.override = { name, args ->
            val key = when (name) {
                "titre" -> "titre-" + args.optString("isin")
                else -> name
            }
            val f = File(ecrans!!, "$key.json")
            if (!f.exists()) Reply.Err("pas de données d'écran pour $key")
            else Reply.parse(f.readText())
        }
    }

    @After
    fun cleanup() {
        Engine.override = null
    }

    private fun capture(name: String, route: String, apres: () -> Unit = {}) {
        sortie.mkdirs()
        lateinit var nav: NavHostController
        rule.setContent {
            PatrimoineTheme {
                nav = rememberNavController()
                AppContent(nav, 0, SyncControl(false, null, null) {})
            }
        }
        rule.runOnUiThread { nav.navigate(route) }
        rule.waitForIdle()
        rule.mainClock.advanceTimeBy(1500)
        rule.waitForIdle()
        apres()
        rule.mainClock.advanceTimeBy(500)
        rule.waitForIdle()
        rule.onRoot().captureRoboImage(File(sortie, "$name.png").path)
    }

    private fun toucher(texte: String) {
        rule.onAllNodesWithText(texte)[0].performScrollTo().performClick()
        rule.waitForIdle()
    }

    /** Touche le premier élément dont le texte commence par [debut] (ex. « Tout voir (n) » dont n dépend du jeu). */
    private fun toucherDebut(debut: String) {
        rule.onAllNodes(hasText(debut, substring = true))[0].performScrollTo().performClick()
        rule.waitForIdle()
    }

    /** Pose le doigt (sans le lever) à la fraction ([fx], [fy]) du graphique tactile [index] parmi les zones défilantes. */
    private fun poser(fx: Float, fy: Float) {
        rule.onRoot().performTouchInput { down(androidx.compose.ui.geometry.Offset(width * fx, height * fy)) }
        rule.waitForIdle()
    }

    /** Fait défiler l'écran Bourse jusqu'à la carte d'indice [i] (0 en-tête, 1 comptes, 2 bloc sombre, 3 performance…). */
    private fun defiler(i: Int) {
        rule.onNode(hasScrollToIndexAction()).performScrollToIndex(i)
        rule.waitForIdle()
    }

    @Test fun accueil() = capture("01-patrimoine", Routes.ACCUEIL)
    @Test fun accueilBas() = capture("01-patrimoine-milieu", Routes.ACCUEIL) { defiler(3) }
    @Test fun accueilComptes() = capture("01-patrimoine-comptes", Routes.ACCUEIL) { defiler(5) }
    @Test fun accueil3M() = capture("01-patrimoine-3m", Routes.ACCUEIL) { toucher("3M") }
    @Test fun accueilDetails() = capture("01-patrimoine-details", Routes.ACCUEIL) { defiler(5); toucherDebut("Afficher") }
    @Test fun accueilDetailsTuile() = capture("01-patrimoine-details-tuile", Routes.ACCUEIL) { defiler(5); toucherDebut("Afficher"); toucherDebut("Gains d'investissement (brut)") }
    @Test fun accueilSansPeg() = capture("01-patrimoine-sans-peg", Routes.ACCUEIL) { toucher("Sans le PEG") }
    @Test fun accueilSansPegDetails() = capture("01-patrimoine-sans-peg-details", Routes.ACCUEIL) { toucher("Sans le PEG"); defiler(5); toucherDebut("Afficher") }
    @Test fun accueilCompteDeplie() = capture("01-patrimoine-compte-deplie", Routes.ACCUEIL) { defiler(6); toucher("Compte-titres") }
    @Test fun accueilInfobulle() = capture("01-patrimoine-infobulle", Routes.ACCUEIL) { poser(0.6f, GY_ACCUEIL) }
    @Test fun fluxInfobulle() = capture("03-flux-infobulle", Routes.DEPENSES) { poser(0.6f, GY_FLUX) }
    @Test fun bourseInfobulle() = capture("02-bourse-infobulle", Routes.BOURSE) { toucher("1A"); poser(0.6f, GY_BOURSE) }
    @Test fun titreInfobulle() = capture("13-titre-infobulle", Routes.titre(ACTION)) { toucher("1A"); poser(0.6f, GY_TITRE) }
    @Test fun bourse() = capture("02-bourse-defaut", Routes.BOURSE)
    @Test fun bourseCartes() = capture("02-bourse-positions", Routes.BOURSE) { defiler(4) }
    @Test fun bourseMilieu() = capture("02-bourse-rendements", Routes.BOURSE) { defiler(5) }
    @Test fun bourseBas() = capture("02-bourse-dividendes", Routes.BOURSE) { defiler(7) }
    @Test fun bourseComptes1A() = capture("02-bourse-comptes-1a", Routes.BOURSE) { toucher("Comptes"); toucher("1A") }
    @Test fun bourseUnComptePct() = capture("02-bourse-compte-pct", Routes.BOURSE) { toucher("Compte-titres"); toucher("%"); toucher("3M") }
    @Test fun bourseUnCompteEuros() = capture("02-bourse-compte-eur-ytd", Routes.BOURSE) { toucher("PEA"); toucher("YTD") }
    @Test fun bourseCompteSansCout() = capture("02-bourse-compte-sans-cout", Routes.BOURSE) { toucher("PEG Airbus"); toucher("1A") }
    @Test fun bourse1JPourcent() = capture("02-bourse-1j-pct", Routes.BOURSE) { toucher("%") }
    @Test fun bourse1JComptes() = capture("02-bourse-1j-comptes", Routes.BOURSE) { toucher("Comptes") }

    // Fiche d'un titre (jeu fictif : une action avec dividende et vente, un titre sans prix de revient)
    @Test fun titre1J() = capture("13-titre-1j", Routes.titre(ACTION))
    @Test fun titre1A() = capture("13-titre-1a-haut", Routes.titre(ACTION)) { toucher("1A") }
    @Test fun titreBas() = capture("13-titre-bas", Routes.titre(ACTION)) { toucher("1A"); defiler(4) }
    @Test fun titreToutVoir() = capture("13-titre-operations", Routes.titre(ACTION)) { toucher("1A"); defiler(4); toucherDebut("Tout voir (") }
    @Test fun titreEtf() = capture("13-titre-etf-3m", Routes.titre(ETF)) { toucher("3M") }
    @Test fun titreSansPrixDeRevient() = capture("13-titre-sans-prix-de-revient", Routes.titre(SANS_COUT)) { toucher("1A") }
    @Test fun titreSansPrixDeRevientBas() = capture("13-titre-sans-prix-de-revient-bas", Routes.titre(SANS_COUT)) { toucher("1A"); defiler(2) }
    @Test fun flux() = capture("03-flux", Routes.DEPENSES)
    @Test fun fluxRevenus() = capture("03-flux-revenus", Routes.DEPENSES) { defiler(2) }
    @Test fun fluxDepenses() = capture("03-flux-depenses", Routes.DEPENSES) { defiler(4) }
    @Test fun fluxParMois() = capture("03-flux-par-mois", Routes.DEPENSES) { defiler(5) }
    @Test fun fluxTaux() = capture("03-flux-taux", Routes.DEPENSES) { defiler(6) }
    @Test fun fluxOperations() = capture("03-flux-operations", Routes.DEPENSES) { defiler(8) }
    @Test fun analyses() = capture("04-analyses", Routes.ANALYSES)
    @Test fun plus() = capture("05-plus", Routes.PLUS)
    @Test fun vendeurs() = capture("06-vendeurs", Routes.VENDEURS)
    @Test fun operations() = capture("07-operations", Routes.OPERATIONS)
    @Test fun projection() = capture("08-projection", Routes.PROJECTION)
    @Test fun ordres() = capture("09-ordres", Routes.ORDRES)
    @Test fun alertes() = capture("10-alertes", Routes.ALERTES)
    @Test fun cartes() = capture("12-titres-restaurant", Routes.CARTES)
    @Test fun reglages() = capture("11-reglages", Routes.REGLAGES)
}
