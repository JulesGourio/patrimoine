package fr.julesgourio.patrimoine

import androidx.compose.ui.test.junit4.createComposeRule
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
    @get:Rule
    val rule = createComposeRule()

    private val ecrans = System.getenv("PATRIMOINE_ECRANS")?.takeIf { it.isNotBlank() }?.let(::File)
    private val sortie = File(System.getenv("PATRIMOINE_CAPTURES") ?: "build/captures")

    @Before
    fun fixtures() {
        assumeTrue("PATRIMOINE_ECRANS non défini : pas de captures", ecrans?.isDirectory == true)
        Engine.override = { name, args ->
            val key = when (name) {
                "cours" -> "cours-" + args.optString("isin")
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

    private fun capture(name: String, route: String) {
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
        rule.onRoot().captureRoboImage(File(sortie, "$name.png").path)
    }

    @Test fun accueil() = capture("01-patrimoine", Routes.ACCUEIL)
    @Test fun portefeuille() = capture("02-portefeuille", Routes.PORTEFEUILLE)
    @Test fun depenses() = capture("03-depenses", Routes.DEPENSES)
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
