#define AppName "ClipNest"
#define AppVersion "1.32"
#define BuildDir "..\..\work\dist-v132\ClipNest"

[Setup]
AppId={{0ED42FB7-3A2F-43B3-B063-BACD9F672671}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName=ClipNest {#AppVersion}
AppPublisher=ClipNest
DefaultDirName={code:InstallDirectory}
DefaultGroupName=ClipNest
UsePreviousAppDir=yes
DisableDirPage=no
PrivilegesRequired=lowest
SetupArchitecture=x64
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\ClipNest.exe
Uninstallable=yes
CreateUninstallRegKey=yes
SetupIconFile=ClipNest.ico
OutputDir=..
OutputBaseFilename=ClipNest-{#AppVersion}-Setup-x64
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
ShowLanguageDialog=no
VersionInfoVersion=1.32.0.0
VersionInfoDescription=ClipNest installer

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务："; Flags: unchecked

[InstallDelete]
; Remove only identified program files from the old portable bundle.
Type: filesandordirs; Name: "{app}\ClipNest-1.20-Windows\ClipNest-1.20\_internal"
Type: files; Name: "{app}\ClipNest-1.20-Windows\ClipNest-1.20\ClipNest.exe"
Type: files; Name: "{app}\ClipNest-1.20-Windows\ClipNest-1.20\ClipNest-icon.png"
Type: files; Name: "{app}\ClipNest-1.20-Windows\ClipNest-1.20\ClipNest.ico"
Type: files; Name: "{app}\ClipNest-1.20-Windows\ClipNest-1.20\clipnest.py"
Type: files; Name: "{app}\ClipNest-1.20-Windows\ClipNest-1.20\ClipNest.spec"
Type: files; Name: "{app}\ClipNest-1.20-Windows\ClipNest-1.20\README.md"
Type: dirifempty; Name: "{app}\ClipNest-1.20-Windows\ClipNest-1.20"
Type: dirifempty; Name: "{app}\ClipNest-1.20-Windows"
; A previous build duplicated Qt DLLs in PySide6 and the runtime root.
Type: files; Name: "{app}\_internal\PySide6\*.dll"
Type: files; Name: "{app}\_internal\shiboken6\*.dll"
Type: files; Name: "{app}\_internal\libcrypto-3.dll"
Type: files; Name: "{app}\_internal\libssl-3.dll"

[Files]
Source: "{#BuildDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\ClipNest"; Filename: "{app}\ClipNest.exe"
Name: "{autoprograms}\卸载 ClipNest"; Filename: "{uninstallexe}"
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

var
  RemoveUserData: Boolean;

function InstallDirectory(Param: String): String;
var
  StartupValue: String;
  ExePath: String;
  ClosingQuote: Integer;
  SwitchPosition: Integer;
begin
  Result := ExpandConstant('{%LOCALAPPDATA}\Programs\ClipNest');
  if not RegQueryStringValue(HKCU, StartupKey, StartupName, StartupValue) then Exit;
  StartupValue := Trim(StartupValue);
  if (Pos('clipnest.exe', Lowercase(StartupValue)) = 0) or
    (Pos('--background', Lowercase(StartupValue)) = 0) then Exit;
  if Copy(StartupValue, 1, 1) = '"' then begin
    ClosingQuote := Pos('"', Copy(StartupValue, 2, Length(StartupValue) - 1));
    if ClosingQuote = 0 then Exit;
    ExePath := Copy(StartupValue, 2, ClosingQuote - 1);
  end else begin
    SwitchPosition := Pos(' --background', Lowercase(StartupValue));
    if SwitchPosition = 0 then Exit;
    ExePath := Copy(StartupValue, 1, SwitchPosition - 1);
  end;
  if (CompareText(ExtractFileName(ExePath), 'ClipNest.exe') = 0) and
    FileExists(ExePath) then
    Result := ExtractFileDir(ExePath);
end;

function InitializeUninstall: Boolean;
var
  Choice: Integer;
begin
  if UninstallSilent then begin
    RemoveUserData := False;
    Result := True;
    Exit;
  end;
  Choice := MsgBox(
    '是否同时删除 ClipNest 的本地剪贴记录和设置？' + #13#10 + #13#10 +
    '是：彻底删除记录、密钥、设置和更新缓存。' + #13#10 +
    '否：保留记录和密钥，以便同一 Windows 账户重装后继续使用。' + #13#10 +
    '取消：停止卸载。' + #13#10 + #13#10 +
    '无论选择哪种方式，已保存的 GitHub 访问令牌都会删除。',
    mbConfirmation, MB_YESNOCANCEL or MB_DEFBUTTON1);
  RemoveUserData := Choice = IDYES;
  Result := Choice <> IDCANCEL;
end;

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
  ExitCode: Integer;
begin
  if CurUninstallStep <> usUninstall then Exit;
  InstalledExe := ExpandConstant('{app}\ClipNest.exe');
  if RegQueryStringValue(HKCU, StartupKey, StartupName, OldValue) then
    if Pos(Lowercase(InstalledExe), Lowercase(OldValue)) > 0 then
      RegDeleteValue(HKCU, StartupKey, StartupName);
  if not FileExists(InstalledExe) then Exit;
  Exec(InstalledExe, '--quit', '', SW_HIDE, ewWaitUntilTerminated, ExitCode);
  Sleep(750);
  if RemoveUserData then begin
    if (not Exec(InstalledExe, '--purge-user-data', '', SW_HIDE,
      ewWaitUntilTerminated, ExitCode)) or (ExitCode <> 0) then
      MsgBox('ClipNest 程序已卸载，但本地记录可能未清除。请检查数据保存目录。',
        mbError, MB_OK);
  end;
end;
