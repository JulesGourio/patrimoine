package fr.julesgourio.patrimoine.ui.components

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyListScope
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import fr.julesgourio.patrimoine.engine.Engine
import fr.julesgourio.patrimoine.engine.Reply
import org.json.JSONObject

/** Bumped when a sync finishes: every screen on show reloads its data. */
val LocalRefresh = staticCompositionLocalOf { 0 }

sealed interface Load {
    data object Loading : Load
    data class Done(val data: JSONObject) : Load
    data class Failed(val message: String) : Load
}

class LoadState(val load: Load, val refreshing: Boolean, val reload: () -> Unit)

/**
 * The result of `Engine.call(name, args)`, reloaded when one of [keys] changes, after a sync, or on [LoadState.reload].
 * The previous data stays on screen while it reloads.
 */
@Composable
fun rememberCall(name: String, args: JSONObject? = null, vararg keys: Any?): LoadState {
    val refresh = LocalRefresh.current
    var reloads by remember { mutableIntStateOf(0) }
    var load by remember(name, *keys) { mutableStateOf<Load>(Load.Loading) }
    var refreshing by remember { mutableStateOf(false) }
    LaunchedEffect(name, refresh, reloads, *keys) {
        refreshing = true
        load = when (val r = Engine.call(name, args ?: JSONObject()).obj()) {
            is Reply.Ok -> Load.Done(r.data as JSONObject)
            is Reply.Err -> if (load is Load.Done) load.also { refreshing = false } else Load.Failed(r.message)
        }
        refreshing = false
    }
    return LoadState(load, refreshing, reload = { reloads++ })
}

/** Spinner, error with a retry button, or the content. */
@Composable
fun Loaded(state: LoadState, content: @Composable (JSONObject) -> Unit) {
    when (val l = state.load) {
        Load.Loading -> Box(Modifier.fillMaxWidth().padding(48.dp), contentAlignment = Alignment.Center) {
            CircularProgressIndicator()
        }
        is Load.Failed -> ErrorBox(l.message, state.reload)
        is Load.Done -> content(l.data)
    }
}

@Composable
fun ErrorBox(message: String, retry: (() -> Unit)? = null) {
    Column(
        Modifier.fillMaxWidth().padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text("Données indisponibles", style = MaterialTheme.typography.titleMedium)
        Text(message, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.error)
        if (retry != null) Button(onClick = retry) { Text("Réessayer") }
    }
}

/** A scrolling screen of one call's data, pulled down to reload. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CallScreen(
    state: LoadState,
    padding: PaddingValues = PaddingValues(0.dp),
    content: LazyListScope.(JSONObject) -> Unit,
) {
    PullToRefreshBox(
        isRefreshing = state.refreshing && state.load is Load.Done,
        onRefresh = state.reload,
        modifier = Modifier.fillMaxSize().padding(padding),
    ) {
        LazyColumn(
            Modifier.fillMaxSize(),
            contentPadding = PaddingValues(horizontal = 16.dp, vertical = 12.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            when (val l = state.load) {
                Load.Loading -> item { Loaded(state) {} }
                is Load.Failed -> item { ErrorBox(l.message, state.reload) }
                is Load.Done -> content(l.data)
            }
        }
    }
}
