Option Explicit
Dim shell, fso, root, command
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName)
command = Chr(34) & root & "\run.bat" & Chr(34)
shell.CurrentDirectory = root
shell.Run command, 0, False
