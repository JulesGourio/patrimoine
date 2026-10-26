import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.chaquopy)
}

android {
    namespace = "fr.julesgourio.patrimoine"
    compileSdk = 36

    defaultConfig {
        applicationId = "fr.julesgourio.patrimoine"
        minSdk = 26
        targetSdk = 36
        // CI sets the run number so every APK installs over the previous one.
        versionCode = (System.getenv("GITHUB_RUN_NUMBER") ?: "1").toInt()
        versionName = "0.1." + (System.getenv("GITHUB_RUN_NUMBER") ?: "0")
        ndk {
            // The Pixel 8a and every recent phone; curl_cffi only ships arm64 wheels for Android.
            abiFilters += listOf("arm64-v8a")
        }
    }

    signingConfigs {
        // One fixed key for every build (CI and PC), so a new APK updates the app instead of
        // requiring an uninstall that would erase its data. Sideloaded app, not published.
        create("patrimoine") {
            storeFile = file("patrimoine.keystore")
            storePassword = "patrimoine"
            keyAlias = "patrimoine"
            keyPassword = "patrimoine"
        }
    }

    buildTypes {
        debug {
            signingConfig = signingConfigs.getByName("patrimoine")
        }
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("patrimoine")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    buildFeatures {
        compose = true
        buildConfig = true
    }
    packaging {
        resources.excludes += "/META-INF/{AL2.0,LGPL2.1}"
    }
}

kotlin {
    compilerOptions {
        jvmTarget.set(JvmTarget.JVM_17)
    }
}

// The Python engine is the repository's own `patrimoine` package, copied at build time (never duplicated in git).
// PC-only modules stay out: the Streamlit helpers, the MCP server and the Windows scheduled tasks.
val copyEngine by tasks.registering(Sync::class) {
    from(rootProject.file("../patrimoine")) {
        exclude("**/__pycache__/**", "ui.py", "mcp_server.py", "tasks.py")
    }
    into(layout.buildDirectory.dir("python-src/patrimoine"))
}
tasks.named("preBuild") { dependsOn(copyEngine) }

chaquopy {
    defaultConfig {
        version = "3.13"
        pip {
            install("-r", "requirements.txt")
        }
    }
    sourceSets {
        getByName("main") {
            srcDir(layout.buildDirectory.dir("python-src"))
        }
    }
}

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.fragment.ktx)
    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.compose.ui)
    implementation(libs.androidx.compose.ui.tooling.preview)
    implementation(libs.androidx.compose.material3)
    implementation(libs.androidx.compose.material.icons)
    implementation(libs.androidx.navigation.compose)
    implementation(libs.androidx.work.runtime.ktx)
    implementation(libs.androidx.biometric)
    debugImplementation(libs.androidx.compose.ui.tooling)
    testImplementation(libs.junit)
}
