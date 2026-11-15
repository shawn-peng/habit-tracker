# Keep kotlinx.serialization runtime and generated serializers
-keepattributes *Annotation*, InnerClasses
-dontnote kotlinx.serialization.AnnotationsKt

-keepclassmembers class kotlinx.serialization.json.** {
    *** Companion;
}
-keepclasseswithmembers class kotlinx.serialization.json.** {
    kotlinx.serialization.KSerializer serializer(...);
}

-keep,includedescriptorclasses class com.shawnpeng.habittracker.data.**$$serializer { *; }
-keepclassmembers class com.shawnpeng.habittracker.data.** {
    *** Companion;
}
-keepclasseswithmembers class com.shawnpeng.habittracker.data.** {
    kotlinx.serialization.KSerializer serializer(...);
}

# OkHttp / Okio
-dontwarn okhttp3.**
-dontwarn okio.**
-dontwarn javax.annotation.**
