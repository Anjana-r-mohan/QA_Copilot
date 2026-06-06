plugins {
    id("java")
    id("org.jetbrains.intellij") version "1.17.2"
    id("org.jetbrains.kotlin.jvm") version "1.9.0"
}

group = "com.bizom"
version = "3.2.1-unified"  // Explicit current-file context messaging and safer plan handling.

repositories {
    mavenCentral()
}

dependencies {
    implementation("com.google.code.gson:gson:2.10.1")
    implementation("com.squareup.okhttp3:okhttp:4.11.0")
}

intellij {
    version.set("2023.3")
    type.set("IU")
    plugins.set(listOf("java"))
    updateSinceUntilBuild.set(false)
}

tasks {
    withType<JavaCompile> {
        sourceCompatibility = "11"
        targetCompatibility = "11"
    }

    buildPlugin {
        archiveFileName.set("script-sherpa-v3.2.1-unified.zip")
    }
}
