#define AppName "ClipNest"
#define AppVersion "1.22"
#define BuildDir "..\..\work\dist-v122\ClipNest"

[Setup]
AppId={{0ED42FB7-3A2F-43B3-B063-BACD9F672671}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName=ClipNest {#AppVersion}
AppPublisher=ClipNest
DefaultDirName={%LOCALAPPDATA}\Programs\ClipNest
DefaultGroupName=ClipNest
UsePreviousAppDir=yes
DisableDirPage=no
PrivilegesRequired=lowest
SetupArchitecture=x64
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\ClipNest.exe
SetupIconFile=ClipNest.ico
OutputDir=..
OutputBaseFilename=ClipNest-{#AppVersion}-Setup-x64
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
ShowLanguageDialog=no
VersionInfoVersion=1.22.0.0
VersionInfoDescription=ClipNest installer

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务："; Flags: unchecked

[Files]
Source: "{#BuildDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\ClipNest"; Filename: "{app}\ClipNest.exe"
Name: "{autodesktop}\ClipNest"; Filename: "{app}\ClipNest.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\ClipNest.exe"; Description: "启动 ClipNest"; Flags: nowait postinstall skipifsilent
Filename: "{app}\ClipNest.exe"; Parameters: "--background"; Flags: nowait skipifnotsilent

[UninstallDelete]
Type: files; Name: "{%LOCALAPPDATA}\ClipNest\github-token.dat"
Type: filesandordirs; Name: "{%LOCALAPPDATA}\ClipNest\updates"

[Code]
const
  StartupKey = 'Software\Microsoft\Windows\CurrentVersion\Run';
  StartupName = 'ClipNest';

function IsClipNestStartup(const Value: String): Boolean;
begin
  Result := (Pos('clipnest.exe', Lowercase(Value)) > 0) and
    (Pos('--background', Lowercase(Value)) > 0);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  OldValue: String;
  NewValue: String;
  ExitCode: Integer;
begin
  if CurStep = ssInstall then begin
    if FileExists(ExpandConstant('{app}\ClipNest.exe')) then begin
      Exec(ExpandConstant('{app}\ClipNest.exe'), '--quit', '', SW_HIDE,
        ewWaitUntilTerminated, ExitCode);
      Sleep(500);
    end;
    Exit;
  end;
  if CurStep <> ssPostInstall then Exit;
  if not RegQueryStringValue(HKCU, StartupKey, StartupName, OldValue) then Exit;
  if not IsClipNestStartup(OldValue) then Exit;
  NewValue := '"' + ExpandConstant('{app}\ClipNest.exe') + '" --background';
  if CompareText(OldValue, NewValue) <> 0 then
    RegWriteStringValue(HKCU, StartupKey, StartupName, NewValue);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  OldValue: String;
  InstalledExe: String;
begin
  if CurUninstallStep <> usUninstall then Exit;
  if not RegQueryStringValue(HKCU, StartupKey, StartupName, OldValue) then Exit;
  InstalledExe := Lowercase(ExpandConstant('{app}\ClipNest.exe'));
  if Pos(InstalledExe, Lowercase(OldValue)) > 0 then
    RegDeleteValue(HKCU, StartupKey, StartupName);
end;

