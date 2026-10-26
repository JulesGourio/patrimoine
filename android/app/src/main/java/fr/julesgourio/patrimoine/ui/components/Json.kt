package fr.julesgourio.patrimoine.ui.components

import org.json.JSONArray
import org.json.JSONObject

// org.json turns JSON null into JSONObject.NULL and optString into "null": these helpers give real nulls.

fun JSONObject.str(key: String): String? =
    if (!has(key) || isNull(key)) null else optString(key).takeUnless { it.isEmpty() }

fun JSONObject.num(key: String): Double? =
    if (!has(key) || isNull(key)) null else optDouble(key).takeUnless { it.isNaN() }

fun JSONObject.int(key: String): Int? = num(key)?.toInt()

fun JSONObject.bool(key: String): Boolean = has(key) && !isNull(key) && optBoolean(key)

fun JSONObject.objOrNull(key: String): JSONObject? = if (!has(key) || isNull(key)) null else optJSONObject(key)

fun JSONObject.list(key: String): List<JSONObject> = optJSONArray(key).objects()

fun JSONObject.strings(key: String): List<String> = optJSONArray(key)?.let { a ->
    (0 until a.length()).mapNotNull { i -> if (a.isNull(i)) null else a.optString(i) }
} ?: emptyList()

fun JSONArray?.objects(): List<JSONObject> =
    if (this == null) emptyList() else (0 until length()).mapNotNull { optJSONObject(it) }

/** Key/value pairs of an object whose values are numbers (e.g. `{"Courses": 412.5}`). */
fun JSONObject.numbers(): List<Pair<String, Double>> =
    keys().asSequence().mapNotNull { k -> num(k)?.let { k to it } }.toList()
