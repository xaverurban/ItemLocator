# ML Kit publishes one text recogniser per script and the Flutter plugin names
# them all. This app only bundles the Latin one, so R8 must not refuse to shrink
# over the classes for scripts that are not on board.
-dontwarn com.google.mlkit.vision.text.chinese.**
-dontwarn com.google.mlkit.vision.text.devanagari.**
-dontwarn com.google.mlkit.vision.text.japanese.**
-dontwarn com.google.mlkit.vision.text.korean.**

# Keep the recogniser itself and the model loading it does by reflection.
-keep class com.google.mlkit.** { *; }
-keep class com.google.android.gms.internal.mlkit_vision_text** { *; }
