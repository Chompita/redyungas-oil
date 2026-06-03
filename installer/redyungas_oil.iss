; ===========================================================================
;  REDYUNGAS OIL — Instalador "todo en uno" (Inno Setup).
;  Empaqueta VLC + Python + git (MinGit) + ffmpeg, CLONA el repo privado, crea
;  el entorno y los accesos directos. La app se AUTOACTUALIZA por git (la lógica
;  ya está en redyungas_oil/core/updater.py: fetch + reset --hard + verificación).
;
;  Cómo compilar (en Windows, con Inno Setup 6 instalado):
;    1) Prepara la carpeta installer\payload\ (ver INSTALADOR.md):
;         payload\vlc-setup.exe        (instalador oficial de VLC 64-bit, renombrado)
;         payload\python-setup.exe     (python-3.11.x-amd64.exe, renombrado)
;         payload\git\...              (MinGit extraído; debe existir git\cmd\git.exe)
;         payload\ffmpeg\ffmpeg.exe    y  payload\ffmpeg\ffprobe.exe
;    2) Abre este .iss en Inno Setup Compiler y pulsa "Compile".
;    3) Sale  Output\RedYungasOil-Setup.exe  → cópialo a cada esclava y ejecútalo.
; ===========================================================================

#define MyAppName "REDYUNGAS OIL"
#define MyAppVersion "1.5.0"
#define MyAppPublisher "Red Yungas"
#define MyRepoDefault "https://github.com/Chompita/redyungas-oil.git"

[Setup]
AppId={{E2C9A1F4-RYO5-4C2A-9B3D-RED0YUNGAS001}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\RedYungasOil
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=Output
OutputBaseFilename=RedYungasOil-Setup
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
WizardStyle=modern
; SetupIconFile=redyungas-oil.ico

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear acceso directo en el Escritorio"; GroupDescription: "Accesos directos:"
Name: "autostart"; Description: "Arrancar REDYUNGAS OIL al iniciar Windows"; GroupDescription: "Inicio:"

[Files]
; Lanzadores y bootstrap (a la carpeta de instalación).
Source: "bootstrap.ps1";          DestDir: "{app}"; Flags: ignoreversion
Source: "RedYungasOil.bat";        DestDir: "{app}"; Flags: ignoreversion
Source: "run_redyungas_oil.vbs";   DestDir: "{app}"; Flags: ignoreversion
; git portátil (MinGit) y ffmpeg → {app}\tools.
Source: "payload\git\*";           DestDir: "{app}\tools\git";    Flags: ignoreversion recursesubdirs createallsubdirs
Source: "payload\ffmpeg\*";        DestDir: "{app}\tools\ffmpeg"; Flags: ignoreversion
; Instaladores que se ejecutan y luego se borran (a {tmp}).
Source: "payload\vlc-setup.exe";    DestDir: "{tmp}"; Flags: deleteafterinstall
Source: "payload\python-setup.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall

[Run]
; 1) VLC en silencio (su instalador es NSIS → /S).
Filename: "{tmp}\vlc-setup.exe"; Parameters: "/S"; StatusMsg: "Instalando VLC…"; Flags: waituntilterminated
; 2) Python en silencio, instalado DENTRO de {app}\python (ruta determinista).
Filename: "{tmp}\python-setup.exe"; \
  Parameters: "/quiet InstallAllUsers=0 PrependPath=0 Include_pip=1 Include_test=0 TargetDir=""{app}\python"""; \
  StatusMsg: "Instalando Python…"; Flags: waituntilterminated
; 3) Bootstrap: clona el repo, crea el venv, instala deps y deja config.toml.
Filename: "powershell.exe"; \
  Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\bootstrap.ps1"" -InstallDir ""{app}"" -RepoUrl ""{code:CloneUrl}"" -Branch master -PythonExe ""{app}\python\python.exe"" -GitExe ""{app}\tools\git\cmd\git.exe"""; \
  StatusMsg: "Descargando y configurando REDYUNGAS OIL…"; Flags: runhidden waituntilterminated
; 4) Lanzar la app al terminar (opcional).
Filename: "wscript.exe"; Parameters: """{app}\run_redyungas_oil.vbs"""; \
  Description: "Iniciar {#MyAppName}"; Flags: postinstall nowait skipifsilent

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "wscript.exe"; Parameters: """{app}\run_redyungas_oil.vbs"""; WorkingDir: "{app}"
Name: "{group}\Editar configuración"; Filename: "notepad.exe"; Parameters: """{app}\repo\config.toml"""; WorkingDir: "{app}"
Name: "{group}\Desinstalar {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "wscript.exe"; Parameters: """{app}\run_redyungas_oil.vbs"""; WorkingDir: "{app}"; Tasks: desktopicon
Name: "{userstartup}\{#MyAppName}"; Filename: "wscript.exe"; Parameters: """{app}\run_redyungas_oil.vbs"""; WorkingDir: "{app}"; Tasks: autostart

[UninstallDelete]
Type: filesandordirs; Name: "{app}\repo"
Type: filesandordirs; Name: "{app}\venv"
Type: filesandordirs; Name: "{app}\python"

[Code]
var
  TokenPage: TInputQueryWizardPage;

procedure InitializeWizard();
begin
  TokenPage := CreateInputQueryPage(wpSelectDir,
    'Credencial del repositorio',
    'Acceso de SOLO LECTURA al repositorio privado',
    'Pega un token de GitHub de SOLO LECTURA (fine-grained PAT con permiso de lectura ' +
    'sobre el repo, o un deploy key como token) y confirma la URL del repositorio. ' +
    'Se usa para clonar y para las actualizaciones (queda cacheado en el clon).');
  TokenPage.Add('Token (solo lectura):', True);
  TokenPage.Add('URL del repositorio:', False);
  TokenPage.Values[1] := '{#MyRepoDefault}';
end;

function CloneUrl(Param: String): String;
var
  token, url: String;
begin
  token := Trim(TokenPage.Values[0]);
  url := Trim(TokenPage.Values[1]);
  if (token <> '') and (Pos('https://', url) = 1) then
    Result := 'https://' + token + '@' + Copy(url, 9, Length(url) - 8)
  else
    Result := url;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = TokenPage.ID then
  begin
    if Trim(TokenPage.Values[0]) = '' then
    begin
      MsgBox('Falta el token de solo lectura para poder clonar el repositorio privado.',
             mbError, MB_OK);
      Result := False;
    end;
  end;
end;
