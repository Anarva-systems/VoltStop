import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

class VoltColors {
  static const background = Color(0xFFF4F3EC);
  static const surface = Color(0xFFFFFEFA);
  static const elevated = Color(0xFFEDF3E6);
  static const border = Color(0xFFDCE3D8);
  static const forest = Color(0xFF1A4035);
  static const lime = Color(0xFFB7DC68);
  // Existing views use green as a foreground color; keep it contrast-safe.
  // Lime remains explicit for accents and selected surfaces.
  static const green = forest;
  // Kept as a source-compatible alias while the driver views migrate to the
  // forest-and-lime palette; it is deliberately not a cyan accent anymore.
  static const cyan = Color(0xFF476E58);
  static const text = Color(0xFF1A4035);
  static const muted = Color(0xFF53685E);
  static const warning = Color(0xFF79580D);
  static const red = Color(0xFFA43A32);
}

const voltSystemUiOverlayStyle = SystemUiOverlayStyle(
  statusBarColor: VoltColors.background,
  statusBarIconBrightness: Brightness.dark,
  statusBarBrightness: Brightness.light,
  systemNavigationBarColor: VoltColors.background,
  systemNavigationBarDividerColor: VoltColors.background,
  systemNavigationBarIconBrightness: Brightness.dark,
);

class VoltSpacing {
  static const xxs = 4.0;
  static const xs = 8.0;
  static const sm = 12.0;
  static const md = 16.0;
  static const lg = 24.0;
  static const xl = 32.0;
  static const xxl = 44.0;
}

class VoltRadii {
  static const field = 15.0;
  static const control = 15.0;
  static const card = 20.0;
  static const pill = 99.0;
}

ThemeData buildVoltStopTheme() {
  final scheme = ColorScheme.fromSeed(
    seedColor: VoltColors.forest,
    brightness: Brightness.light,
    surface: VoltColors.surface,
  ).copyWith(
    primary: VoltColors.forest,
    onPrimary: VoltColors.surface,
    secondary: VoltColors.lime,
    onSecondary: VoltColors.forest,
    surface: VoltColors.surface,
    onSurface: VoltColors.text,
    outline: VoltColors.border,
    error: VoltColors.red,
    onError: VoltColors.surface,
  );

  const headline = TextStyle(
    color: VoltColors.text,
    fontFamily: 'serif',
    fontWeight: FontWeight.w600,
    letterSpacing: -0.7,
    height: 1.08,
  );
  const strongTitle = TextStyle(
    color: VoltColors.text,
    fontWeight: FontWeight.w700,
    letterSpacing: -0.2,
  );

  final inputBorder = OutlineInputBorder(
    borderRadius: BorderRadius.circular(VoltRadii.field),
    borderSide: const BorderSide(color: VoltColors.border),
  );

  return ThemeData(
    useMaterial3: true,
    brightness: Brightness.light,
    colorScheme: scheme,
    scaffoldBackgroundColor: VoltColors.background,
    dividerColor: VoltColors.border,
    appBarTheme: const AppBarTheme(
      backgroundColor: VoltColors.surface,
      foregroundColor: VoltColors.text,
      centerTitle: false,
      elevation: 0,
      scrolledUnderElevation: 0,
      surfaceTintColor: Colors.transparent,
      systemOverlayStyle: voltSystemUiOverlayStyle,
      titleTextStyle: strongTitle,
    ),
    cardTheme: CardThemeData(
      color: VoltColors.surface,
      elevation: 0,
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(VoltRadii.card),
        side: const BorderSide(color: VoltColors.border),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: VoltColors.surface,
      labelStyle: const TextStyle(color: VoltColors.muted),
      hintStyle: const TextStyle(color: VoltColors.muted),
      prefixIconColor: VoltColors.forest,
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
      border: inputBorder,
      enabledBorder: inputBorder,
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(VoltRadii.field),
        borderSide: const BorderSide(color: VoltColors.forest, width: 1.5),
      ),
      errorBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(VoltRadii.field),
        borderSide: const BorderSide(color: VoltColors.red),
      ),
      focusedErrorBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(VoltRadii.field),
        borderSide: const BorderSide(color: VoltColors.red, width: 1.5),
      ),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: VoltColors.forest,
        foregroundColor: VoltColors.surface,
        disabledBackgroundColor: VoltColors.border,
        disabledForegroundColor: VoltColors.muted,
        minimumSize: const Size(48, 54),
        padding: const EdgeInsets.symmetric(horizontal: 20),
        textStyle: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(VoltRadii.control),
        ),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: VoltColors.forest,
        minimumSize: const Size(48, 50),
        side: const BorderSide(color: VoltColors.border),
        textStyle: const TextStyle(fontWeight: FontWeight.w700, fontSize: 14),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(VoltRadii.control),
        ),
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        foregroundColor: VoltColors.forest,
        textStyle: const TextStyle(fontWeight: FontWeight.w700, fontSize: 14),
      ),
    ),
    sliderTheme: SliderThemeData(
      activeTrackColor: VoltColors.forest,
      inactiveTrackColor: VoltColors.border,
      thumbColor: VoltColors.forest,
      overlayColor: VoltColors.lime.withValues(alpha: 0.28),
      valueIndicatorColor: VoltColors.forest,
      valueIndicatorTextStyle: const TextStyle(
          color: VoltColors.surface, fontWeight: FontWeight.w700),
    ),
    progressIndicatorTheme: const ProgressIndicatorThemeData(
      color: VoltColors.forest,
      linearTrackColor: VoltColors.border,
    ),
    navigationBarTheme: NavigationBarThemeData(
      height: 72,
      backgroundColor: VoltColors.surface,
      indicatorColor: VoltColors.elevated,
      elevation: 0,
      labelBehavior: NavigationDestinationLabelBehavior.alwaysShow,
      labelTextStyle: WidgetStateProperty.resolveWith((states) => TextStyle(
            color: VoltColors.forest,
            fontWeight: states.contains(WidgetState.selected)
                ? FontWeight.w700
                : FontWeight.w500,
            fontSize: 11,
          )),
    ),
    chipTheme: ChipThemeData(
      backgroundColor: VoltColors.elevated,
      selectedColor: VoltColors.lime,
      disabledColor: VoltColors.elevated,
      side: const BorderSide(color: VoltColors.border),
      labelStyle: const TextStyle(color: VoltColors.text, fontSize: 12),
      secondaryLabelStyle: const TextStyle(color: VoltColors.forest),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(VoltRadii.control),
      ),
    ),
    tabBarTheme: const TabBarThemeData(
      labelColor: VoltColors.forest,
      unselectedLabelColor: VoltColors.muted,
      indicatorColor: VoltColors.forest,
      dividerColor: VoltColors.border,
      indicatorSize: TabBarIndicatorSize.label,
      labelStyle: TextStyle(fontWeight: FontWeight.w700),
    ),
    snackBarTheme: SnackBarThemeData(
      backgroundColor: VoltColors.forest,
      contentTextStyle: const TextStyle(color: VoltColors.surface),
      behavior: SnackBarBehavior.floating,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(VoltRadii.control),
      ),
    ),
    textTheme: TextTheme(
      displaySmall: headline.copyWith(fontSize: 42),
      headlineMedium: headline.copyWith(fontSize: 34),
      headlineSmall: headline.copyWith(fontSize: 28, letterSpacing: -0.4),
      titleLarge: strongTitle.copyWith(fontSize: 20),
      titleMedium: strongTitle.copyWith(fontSize: 16),
      titleSmall: strongTitle.copyWith(fontSize: 14),
      bodyLarge: TextStyle(color: VoltColors.text, fontSize: 16, height: 1.5),
      bodyMedium: TextStyle(color: VoltColors.text, fontSize: 14, height: 1.45),
      bodySmall: TextStyle(color: VoltColors.muted, fontSize: 12, height: 1.4),
      labelLarge: TextStyle(
        color: VoltColors.forest,
        fontSize: 13,
        fontWeight: FontWeight.w700,
      ),
    ),
  );
}
