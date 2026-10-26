package fr.julesgourio.patrimoine.engine

import android.content.Context
import android.net.Uri
import android.provider.OpenableColumns
import java.io.File

/** Picked documents arrive as content URIs; the engine reads plain files, under their real names. */
object Files {
    fun displayName(context: Context, uri: Uri): String? =
        context.contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { c ->
            if (c.moveToFirst()) c.getString(0) else null
        }

    /** Copy into a fresh cache folder; the name is kept (the engine sorts and recognises files by name). */
    fun toCache(context: Context, uri: Uri, fallbackName: String): File {
        val name = (displayName(context, uri) ?: fallbackName).replace(Regex("[/\\\\]"), "_")
        val dir = File(context.cacheDir, "imports/${System.nanoTime()}").apply { mkdirs() }
        val out = File(dir, name)
        context.contentResolver.openInputStream(uri).use { input ->
            requireNotNull(input) { "fichier illisible" }
            out.outputStream().use { input.copyTo(it) }
        }
        return out
    }

    fun copyToUri(context: Context, file: File, uri: Uri) {
        context.contentResolver.openOutputStream(uri, "w").use { output ->
            requireNotNull(output) { "impossible d'écrire le fichier" }
            file.inputStream().use { it.copyTo(output) }
        }
    }
}
