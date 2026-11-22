; Inno Setup script for the HammerSlip installer.
; Built by build.ps1:  ISCC.exe /DAppVersion=1.9.0 installer\setup.iss

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef Suffix
  #define Suffix ""
#endif
#define AppName "HammerSlip"
#define AppExe  "HammerSlip.exe"
; The user's settings and logs.
#define DataDir "{userdocs}\HammerSlip"

[Setup]
; Never change AppId: it's how Windows knows a new version replaces the old one.
AppId={{1A2E70FF-AF51-4B07-B2C6-A78F626EA288}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
; Installs just for the current user, so no administrator prompt is needed.
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\{#AppName}
DisableProgramGroupPage=yes
DisableDirPage=yes
OutputDir=..\dist
OutputBaseFilename=HammerSlip-Setup-{#AppVersion}{#Suffix}
SetupIconFile=..\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[InstallDelete]
; Clear out the previous version's program files before installing the new one.
Type: filesandordirs; Name: "{app}\*.dll"
Type: filesandordirs; Name: "{app}\*.pyd"

[Files]
Source: "..\build\app.dist\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "..\README.md"; DestDir: "{app}"; DestName: "README.txt"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon
; The uninstaller, next to the user's settings and logs.
Name: "{#DataDir}\Uninstall {#AppName}"; Filename: "{uninstallexe}"; IconFilename: "{app}\{#AppExe}"; Comment: "Completely remove {#AppName} from this computer"
Name: "{autoprograms}\Uninstall {#AppName}"; Filename: "{uninstallexe}"; IconFilename: "{app}\{#AppExe}"

[UninstallDelete]
; A complete clean-up: everything the app created, not just the files the installer put there.
; (Installing a newer version never runs this, so updates keep settings and sales logs.)
Type: filesandordirs; Name: "{#DataDir}"
Type: filesandordirs; Name: "{app}"
; The saved Whatnot token (kept outside Documents so it's never shared by accident).
Type: filesandordirs; Name: "{localappdata}\{#AppName}"

[Messages]
ConfirmUninstall=This will completely remove %1 from this computer, including everything it saved in Documents\HammerSlip:%n%n  •  settings and your saved Whatnot token%n  •  all sales logs (including the Sales Logs folder)%n  •  saved label images and log files%n%nIf you want to keep any sales logs, copy them somewhere else first.%n%nRemove everything?

[Run]
Filename: "{app}\{#AppExe}"; Description: "Start {#AppName} now"; Flags: nowait postinstall skipifsilent
; Updates from inside the app run this installer silently; start the new version afterwards.
Filename: "{app}\{#AppExe}"; Flags: nowait; Check: WizardSilent

[Code]
// Close the app if it's running, so none of its files are in use.
procedure CloseApp();
var
  Code: Integer;
begin
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/f /im "{#AppExe}"', '', SW_HIDE,
       ewWaitUntilTerminated, Code);
end;

function InitializeSetup(): Boolean;
begin
  CloseApp();
  Result := True;
end;

function InitializeUninstall(): Boolean;
begin
  CloseApp();
  Result := True;
end;
