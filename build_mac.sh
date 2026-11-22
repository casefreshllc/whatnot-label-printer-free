#!/bin/bash
# Builds the Mac (Apple Silicon) app and its .dmg.
#   1. Nuitka compiles app.py into  build/app.app, renamed to "HammerSlip.app"
#   2. A few Mac settings are added (bundle id, App Nap off) and the app is re-signed (ad-hoc)
#   3. The app is packed into  dist/HammerSlip-<version>-mac<suffix>.dmg
#      with a shortcut to Applications so people can drag it in.
#
# GitHub runs this automatically (see .github/workflows/build.yml). On a Mac you can run it with:
#   pip install -r requirements.txt nuitka && bash build_mac.sh
set -euo pipefail
cd "$(dirname "$0")"

APP_NAME="HammerSlip"
VERSION="$(python -c 'import paths; print(paths.VERSION)')"
SUFFIX="$(printf '%s' "${INSTALLER_SUFFIX:-}" | sed 's/[^A-Za-z0-9._-]/-/g')"
echo "Building $APP_NAME $VERSION for Mac (Apple Silicon)"

rm -rf build/app.app "build/$APP_NAME.app" dist/*.dmg dmg-stage
python -m nuitka app.py \
  --mode=app \
  --assume-yes-for-downloads \
  --enable-plugin=tk-inter \
  --macos-target-arch=arm64 \
  --macos-app-name="$APP_NAME" \
  --macos-app-version="$VERSION" \
  --macos-app-icon=icon.icns \
  --macos-app-mode=gui \
  --macos-app-macos-min-version=13.0 \
  --include-data-files=config.json=config.json \
  --output-dir=build

APP="build/$APP_NAME.app"
mv build/app.app "$APP"
PLIST="$APP/Contents/Info.plist"
set_plist() {  # key type value: set it, or add it if it isn't there yet
  /usr/libexec/PlistBuddy -c "Set :$1 $3" "$PLIST" 2>/dev/null \
    || /usr/libexec/PlistBuddy -c "Add :$1 $2 $3" "$PLIST"
}
set_plist CFBundleIdentifier string com.casefresh.hammerslip
set_plist CFBundleDisplayName string "$APP_NAME"
set_plist CFBundleName string "$APP_NAME"
set_plist CFBundleShortVersionString string "$VERSION"
set_plist CFBundleVersion string "$VERSION"
# Keep macOS from slowing the app down (App Nap) when its window is behind the browser.
set_plist NSAppSleepDisabled bool true
set_plist LSMinimumSystemVersion string 13.0

# Changing Info.plist breaks the signature Nuitka made, so sign again (ad-hoc: Apple Silicon
# requires every app to be signed, even unofficially).
codesign --force --deep --sign - "$APP"
codesign --verify --deep --strict "$APP"

mkdir -p dist dmg-stage
cp -R "$APP" dmg-stage/
ln -s /Applications dmg-stage/Applications
cp README.md "dmg-stage/README.txt"
cp LICENSE "dmg-stage/LICENSE.txt"
hdiutil create -volname "$APP_NAME" -srcfolder dmg-stage -ov -format UDZO \
  "dist/HammerSlip-$VERSION-mac$SUFFIX.dmg"
rm -rf dmg-stage
ls -la dist
