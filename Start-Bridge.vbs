Option Explicit
Dim shell, fso, root, command
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = root
command = "pythonw.exe " & Chr(34) & root & "\bridge\launch.pyw" & Chr(34)
On Error Resume Next
shell.Run command, 0, False
If Err.Number <> 0 Then
    MsgBox "Could not start Python. Install Python with Tkinter, then run Setup.cmd." & vbCrLf & Err.Description, 16, "WoW LLM Chat"
End If
