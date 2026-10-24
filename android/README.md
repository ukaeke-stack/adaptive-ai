# Adaptive AI Android companion

This native Android project is the foundation for a true system-wide robot overlay; a web page alone cannot draw over other apps. It wraps the production Adaptive AI web interface in a WebView and adds an opt-in Android foreground service that draws a full-body humanoid robot, animates a walking gait, roams horizontally, and can be dragged. A persistent Android notification indicates the service is active.

## Build and install

- Open the `android/` folder in Android Studio with JDK 17 and Android SDK 35.
- Build the `app` debug APK.
- Install it, open Adaptive AI, tap **Enable roaming robot**, and grant **Display over other apps**. Return to the app and tap the control again.

## Current milestone limits

- The overlay can stay above other apps while Android allows the foreground service to run. Force-stop, some battery managers, or system policy may stop it.
- Tapping the robot opens Adaptive AI's chat activity. The overlay does not yet have its own mini-chat panel, so this milestone does not yet meet the requirement to talk directly through the robot without opening the app.
- Hands-free continuous conversation depends on Android WebView speech-recognition support and microphone permission. Screen-off/background microphone use is not enabled in this milestone.
- No credentials or API tokens are embedded in the app.
