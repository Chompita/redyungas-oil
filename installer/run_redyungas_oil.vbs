' REDYUNGAS OIL — arranca el lanzador .bat de forma OCULTA (sin parpadeo de consola).
' A esto apuntan los accesos directos (Escritorio e Inicio/autoarranque).
Set sh = CreateObject("WScript.Shell")
base = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\"))
sh.Run """" & base & "RedYungasOil.bat""", 0, False
