Option Explicit
Dim swApp, model, partDoc, planeFeature, sketchManager, segment, feature
Dim template, scriptFolder, outputFile, errors, warnings, savedStatus
Dim autoRelationsOriginal, selected, segmentIndex, createdCount, featureIndex
Dim logFile, fso, stamp, sketchIndex, candidateFeature, splinePoints
Dim axisSegment, selectionData
On Error Resume Next
Set fso = CreateObject("Scripting.FileSystemObject")
Set logFile = fso.CreateTextFile(fso.GetParentFolderName(WScript.ScriptFullName) & "\CADView-builder-log.txt", True)
On Error GoTo 0
If logFile Is Nothing Then Err.Raise vbObjectError + 9, , "Could not create CADView-builder-log.txt"
logFile.WriteLine "CAD-View SolidWorks builder log"
On Error Resume Next
Set swApp = Nothing
Set swApp = GetObject(, "SldWorks.Application")
On Error GoTo 0
If swApp Is Nothing Then
  Set swApp = CreateObject("SldWorks.Application")
  logFile.WriteLine "sw_connect=CreateObject"
Else
  logFile.WriteLine "sw_connect=GetObject"
End If
swApp.Visible = True
swApp.UserControl = True
swApp.DocumentVisible True, 1
autoRelationsOriginal = swApp.GetUserPreferenceToggle(53)
swApp.SetUserPreferenceToggle 53, False
template = swApp.GetUserPreferenceStringValue(8)
If Len(template) = 0 Then Err.Raise vbObjectError + 1, , "No default SolidWorks part template is configured."
logFile.WriteLine "template=" & template
Set model = swApp.NewDocument(template, 0, 0, 0)
If model Is Nothing Then Err.Raise vbObjectError + 2, , "SolidWorks could not create a part document."
WScript.Sleep 800
model.Visible = True
logFile.WriteLine "doc_title=" & model.GetTitle()
Set partDoc = model
Set sketchManager = model.SketchManager
featureIndex = 1
logFile.WriteLine "feature_start=1:CADView Core Revolve"
logFile.WriteLine "sketch_start=feature_1_profile"
model.ClearSelection2 True
selected = False
Set planeFeature = partDoc.FeatureByName("Front Plane")
If Not planeFeature Is Nothing Then selected = planeFeature.Select2(False, 0)
If Not selected Then selected = model.Extension.SelectByID2("Front Plane", "PLANE", 0, 0, 0, False, 0, Nothing, 0)
If Not selected Then Err.Raise vbObjectError + 3, , "Could not select Front Plane for feature_1_profile."
sketchManager.InsertSketch True
WScript.Sleep 200
If sketchManager.ActiveSketch Is Nothing Then
  model.InsertSketch2 True
  WScript.Sleep 300
End If
Set segment = sketchManager.CreateLine(0, 0, 0, 0.01, 0, 0)
logFile.WriteLine "probe_line=" & (Not segment Is Nothing)
If segment Is Nothing And sketchManager.ActiveSketch Is Nothing Then
  Err.Raise vbObjectError + 8, , "SolidWorks did not enter sketch mode for feature_1_profile."
End If
If Not segment Is Nothing Then
  segment.Select4 False, Nothing
  model.EditDelete
End If
model.SetAddToDB True
model.SetDisplayWhenAdded False
sketchManager.AddToDB = True
sketchManager.DisplayWhenAdded = False
segmentIndex = 0
createdCount = 0
Set axisSegment = Nothing
logFile.WriteLine "feature_1_profile_outer_points=13"
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.004490823797328119, 0, 0, 0.004490823797328119, 0.00025090543741613163, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.004490823797328119, 0.00025090543741613163, 0, 0.0053447427110394838, 0.00075271631224839485, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0053447427110394838, 0.00075271631224839485, 0, 0.0056074571080781486, 0.0012545271870806581, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0056074571080781486, 0.0012545271870806581, 0, 0.0057868707406516654, 0.016308853432048558, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0057868707406516654, 0.016308853432048558, 0, 0.0059329617682822655, 0.01781428605654535, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0059329617682822655, 0.01781428605654535, 0, 0.0062814485231683153, 0.018316096931377607, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0062814485231683153, 0.018316096931377607, 0, 0.0063568076948287847, 0.031864990551848722, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0063568076948287847, 0.031864990551848722, 0, 0.0066253243952995771, 0.036381288425339088, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0066253243952995771, 0.036381288425339088, 0, 0.0032218890496578238, 0.036883099300171356, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0032218890496578238, 0.036883099300171356, 0, 0.0019238612646513998, 0.048173843983897277, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0019238612646513998, 0.048173843983897277, 0, 0, 0.048173843983897277, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0, 0.048173843983897277, 0, 0, 0, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0, 0, 0, 0.004490823797328119, 0, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
Set axisSegment = sketchManager.CreateCenterLine(0, 0, 0, 0, 0.048173843983897277, 0)
If axisSegment Is Nothing Then Err.Raise vbObjectError + 15, , "Could not create the feature_1_profile revolve centerline."
logFile.WriteLine "feature_1_profile_centerline=created"
logFile.WriteLine "segments_attempted=" & segmentIndex
logFile.WriteLine "segments_non_nothing=" & createdCount
model.SetAddToDB False
model.SetDisplayWhenAdded True
sketchManager.AddToDB = False
sketchManager.DisplayWhenAdded = True
model.ViewZoomtofit2
sketchManager.InsertSketch True
Set planeFeature = Nothing
For sketchIndex = 1 To 100
Set candidateFeature = Nothing
On Error Resume Next
  Set candidateFeature = partDoc.FeatureByName("Sketch" & sketchIndex)
On Error GoTo 0
  If Not candidateFeature Is Nothing Then Set planeFeature = candidateFeature
Next
If planeFeature Is Nothing Then Err.Raise vbObjectError + 10, , "Could not find feature_1_profile."
planeFeature.Name = "CADView Revolve Profile"
logFile.WriteLine "sketch_ok=feature_1_profile"
model.ClearSelection2 True
selected = model.Extension.SelectByID2("CADView Revolve Profile", "SKETCH", 0, 0, 0, False, 0, Nothing, 0)
If Not selected Then Err.Raise vbObjectError + 16, , "Could not select the revolve profile sketch."
If axisSegment Is Nothing Then Err.Raise vbObjectError + 17, , "The revolve sketch has no centerline to revolve about."
Set selectionData = model.SelectionManager.CreateSelectData
selectionData.Mark = 4
axisSegment.Select4 True, selectionData
Set feature = model.FeatureManager.FeatureRevolve2(True, True, False, False, False, False, 0, 0, 6.2831853071795862, 0, False, False, 0, 0, 0, 0, 0, True, True, True)
If feature Is Nothing Then
  Err.Raise vbObjectError + 18, , "SolidWorks rejected the recovered Revolve."
End If
feature.Name = "CADView Core Revolve"
model.EditRebuild3
logFile.WriteLine "feature_ok=1:revolve"
model.ForceRebuild3 True
scriptFolder = fso.GetParentFolderName(WScript.ScriptFullName)
stamp = Year(Now) & Right("0" & Month(Now), 2) & Right("0" & Day(Now), 2) & "-" & Right("0" & Hour(Now), 2) & Right("0" & Minute(Now), 2) & Right("0" & Second(Now), 2)
outputFile = scriptFolder & "\CADView-editable-" & stamp & ".SLDPRT"
savedStatus = model.SaveAs3(outputFile, 0, 1)
logFile.WriteLine "save_status=" & savedStatus
If savedStatus <> 0 Or Not fso.FileExists(outputFile) Then
  Err.Raise vbObjectError + 7, , "SolidWorks SaveAs3 failed. Status: " & savedStatus
End If
swApp.SetUserPreferenceToggle 53, autoRelationsOriginal
logFile.WriteLine "saved=" & outputFile
logFile.Close
MsgBox "Editable SolidWorks part is open in SolidWorks with 1 native features." & vbCrLf & vbCrLf & "Saved as:" & vbCrLf & outputFile & vbCrLf & vbCrLf & "Do not double-click the file from Explorer while SolidWorks still has it open.", vbInformation, "CAD-View"
