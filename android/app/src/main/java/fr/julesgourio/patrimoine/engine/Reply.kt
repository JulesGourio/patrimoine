package fr.julesgourio.patrimoine.engine

import org.json.JSONObject

/** What every Python bridge function returns: `{"ok": true, "data": …}` or `{"ok": false, "erreur": "…"}`. */
sealed interface Reply {
    data class Ok(val data: Any?) : Reply
    data class Err(val message: String) : Reply

    /** The data as an object, or an error when it is something else. */
    fun obj(): Reply = when (this) {
        is Ok -> if (data is JSONObject) this else Err("réponse inattendue")
        is Err -> this
    }

    companion object {
        fun parse(raw: String): Reply = try {
            val o = JSONObject(raw)
            if (o.optBoolean("ok")) Ok(o.opt("data").takeUnless { it == JSONObject.NULL })
            else Err(o.optString("erreur").ifBlank { "erreur inconnue" })
        } catch (e: Exception) {
            Err("réponse illisible : ${e.message}")
        }
    }
}
