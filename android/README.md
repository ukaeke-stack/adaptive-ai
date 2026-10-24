# Adaptive AI Android companion

This native Android project provides the system-level floating robot that a webpage cannot create by itself. It wraps the production Adaptive AI interface in a WebView and adds an opt-in Android foreground service. The full-body humanoid robot walks across the screen, can be dragged, stays above other apps while Android permits it, and opens a floating chat panel when tapped. The panel loads Adaptive AI directly so a user can start or continue a conversation without navigating back to the full-screen app.

## Build and install

- Open the android/ folder in Android Studio with JDK 17 and Android SDK 35.
- Build the app debug APK.
- Install it and open Adaptive AI.
- Tap Enable roaming robot. Grant microphone permission and Android's Display over other apps permission when requested, then tap the control again if Android returns to the settings screen.
- Tap the walking robot to show or hide the floating chat panel. Keep the ongoing notification visible while the robot is active.

## Limits

- The overlay can remain above other apps while Android allows the foreground service to run. Force-stop, some battery managers, or system policy can stop it.
- Voice use in the floating panel requires microphone permission and WebView speech-recognition support. Android may restrict microphone use while the screen is off or the device is locked.
- The panel uses the same production /app/ web interface; the user must sign in if there is no valid session.
- No API credentials or tokens are embedded in the app.
