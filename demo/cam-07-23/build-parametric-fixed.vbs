Option Explicit
Dim swApp, model, partDoc, planeFeature, sketchManager, segment, feature
Dim template, scriptFolder, outputFile, errors, warnings, savedStatus
Dim autoRelationsOriginal, selected, segmentIndex, createdCount, featureIndex
Dim logFile, fso, stamp, sketchIndex, candidateFeature, splinePoints
Dim axisSegment, selectionData, fallbackUsed
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
logFile.WriteLine "feature_start=1:CADView Outer Extrude"
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
logFile.WriteLine "feature_1_profile_outer_points=59"
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.011316671451889783, 0.01663304294662795, 0, -0.010603020749225853, 0.017695773816552698, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.010603020749225853, 0.017695773816552698, 0, -0.0098667140562085972, 0.018633116203780702, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.0098667140562085972, 0.018633116203780702, 0, -0.0089366205022227314, 0.019639783075421052, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.0089366205022227314, 0.019639783075421052, 0, -0.0080957649768528799, 0.020411818427487766, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.0080957649768528799, 0.020411818427487766, 0, -0.0071574102641859573, 0.021143035223062299, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.0071574102641859573, 0.021143035223062299, 0, -0.0061780479694849904, 0.021781769759501302, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.0061780479694849904, 0.021781769759501302, 0, -0.0051490962268214528, 0.022332891159709, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.0051490962268214528, 0.022332891159709, 0, -0.0041059575713080455, 0.022778757176376549, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.0041059575713080455, 0.022778757176376549, 0, -0.003108272568073825, 0.023106289886996687, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.003108272568073825, 0.023106289886996687, 0, -0.0018789827824024408, 0.023386417578880988, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.0018789827824024408, 0.023386417578880988, 0, -0.0008837401755548449, 0.023518351999744488, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.0008837401755548449, 0.023518351999744488, 0, 0.00019380088568887022, 0.023563122304212945, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.00019380088568887022, 0.023563122304212945, 0, 0.0012588576928248365, 0.02350749521309578, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0012588576928248365, 0.02350749521309578, 0, 0.0022497638994121221, 0.023362613451760526, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0022497638994121221, 0.023362613451760526, 0, 0.0036843204771666205, 0.022983644902790371, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0036843204771666205, 0.022983644902790371, 0, 0.0046048032638970893, 0.02262245009660831, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0046048032638970893, 0.02262245009660831, 0, 0.0055798724420898808, 0.022120368795183112, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0055798724420898808, 0.022120368795183112, 0, 0.0063673776295947275, 0.021612943058940667, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0063673776295947275, 0.021612943058940667, 0, 0.0071537901245575727, 0.020989465058218429, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0071537901245575727, 0.020989465058218429, 0, 0.0078670538429849411, 0.020295647324018371, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0078670538429849411, 0.020295647324018371, 0, 0.008502101452407167, 0.019537028860646781, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.008502101452407167, 0.019537028860646781, 0, 0.0093000843484639904, 0.01828334876905361, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0093000843484639904, 0.01828334876905361, 0, 0.0097083292576322835, 0.017405716614947005, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0097083292576322835, 0.017405716614947005, 0, 0.010028405008652834, 0.016465661248360249, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.010028405008652834, 0.016465661248360249, 0, 0.010231995495211251, 0.015566735582019153, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.010231995495211251, 0.015566735582019153, 0, 0.010343005976788141, 0.014625895572848557, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.010343005976788141, 0.014625895572848557, 0, 0.010352279483851288, 0.01368477259937065, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.010352279483851288, 0.01368477259937065, 0, 0.010264651364997093, 0.012785738632118659, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.010264651364997093, 0.012785738632118659, 0, 0.010087386402877273, 0.011915686378943389, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.010087386402877273, 0.011915686378943389, 0, 0.0098424078087326547, 0.01114108957995324, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0098424078087326547, 0.01114108957995324, 0, 0.0094403626242633154, 0.010212331036098667, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0094403626242633154, 0.010212331036098667, 0, 0.0089717625089997272, 0.0094117399877182845, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0089717625089997272, 0.0094117399877182845, 0, 0.0084258007752355379, 0.0086827021067157027, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0084258007752355379, 0.0086827021067157027, 0, 0.0078039133724025619, 0.008023165742957878, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0078039133724025619, 0.008023165742957878, 0, 0.0070332003030134519, 0.0073857512953488238, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0070332003030134519, 0.0073857512953488238, 0, 0.0063820550627099858, 0.0069542666236389432, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0063820550627099858, 0.0069542666236389432, 0, 0.0056266964571843438, 0.006565733167573337, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0056266964571843438, 0.006565733167573337, 0, 0.0048183037954213021, 0.006258607750608481, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0048183037954213021, 0.006258607750608481, 0, 0.0039125653328124432, 0.0060310102673528229, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0039125653328124432, 0.0060310102673528229, 0, 0.0030323550743356787, 0.0059215955383578479, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0030323550743356787, 0.0059215955383578479, 0, 0.0021492596258059029, 0.0059178743639879388, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0021492596258059029, 0.0059178743639879388, 0, 0.00088016666437320894, 0.0061018601279562218, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.00088016666437320894, 0.0061018601279562218, 0, 0.00011480966149006023, 0.006326575438560033, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.00011480966149006023, 0.006326575438560033, 0, -0.00062609244264671255, 0.006639550089086981, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.00062609244264671255, 0.006639550089086981, 0, -0.0013775865837277333, 0.007065699196514303, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.0013775865837277333, 0.007065699196514303, 0, -0.0020835388966346782, 0.0075912250151642362, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.0020835388966346782, 0.0075912250151642362, 0, -0.0026926703711281147, 0.0081750278437120235, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.0026926703711281147, 0.0081750278437120235, 0, -0.014659380116952513, -0.0044608078780434164, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.014659380116952513, -0.0044608078780434164, 0, -0.014737756643026205, 0.00039505482958423246, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.014737756643026205, 0.00039505482958423246, 0, -0.014706066360585088, 0.0029248374486365537, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.014706066360585088, 0.0029248374486365537, 0, -0.014598510048991424, 0.0050732043471109047, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.014598510048991424, 0.0050732043471109047, 0, -0.014448125852961935, 0.0067504037403766362, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.014448125852961935, 0.0067504037403766362, 0, -0.014219247163917299, 0.0084213729812907586, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.014219247163917299, 0.0084213729812907586, 0, -0.013873475296993001, 0.010186424490309466, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.013873475296993001, 0.010186424490309466, 0, -0.013539941342076036, 0.011501264751420159, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.013539941342076036, 0.011501264751420159, 0, -0.013093836163746913, 0.012897584243516093, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.013093836163746913, 0.012897584243516093, 0, -0.012580769057132568, 0.014202100216322287, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.012580769057132568, 0.014202100216322287, 0, -0.012033376203000568, 0.015358462627681403, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.012033376203000568, 0.015358462627681403, 0, -0.011316671451889783, 0.01663304294662795, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
Set segment = sketchManager.CreateCircleByRadius(0.0019692015525909841, 0.013141593651526026, 0, 0.00074995594522723954)
If Not segment Is Nothing Then createdCount = createdCount + 1
logFile.WriteLine "feature_1_profile_inner_circle_1=attempted"
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
planeFeature.Name = "CADView Outer Profile"
logFile.WriteLine "sketch_ok=feature_1_profile"
Set feature = model.FeatureManager.FeatureExtrusion3(True, False, False, 6, 0, 0.0050084706328932483, 0, False, False, False, True, 0, 0, False, False, False, False, True, False, True, 0, 0, False)
If feature Is Nothing Then
  Err.Raise vbObjectError + 6, , "SolidWorks rejected feature 1 after " & segmentIndex & " line attempts (" & createdCount & " non-Nothing returns; expected about 29)."
End If
feature.Name = "CADView Outer Extrude"
model.EditRebuild3
logFile.WriteLine "feature_ok=1"
featureIndex = 2
logFile.WriteLine "feature_start=2:CADView Perimeter Sweep Cut"
logFile.WriteLine "sketch_start=feature_2_path"
model.ClearSelection2 True
selected = False
Set planeFeature = partDoc.FeatureByName("Front Plane")
If Not planeFeature Is Nothing Then selected = planeFeature.Select2(False, 0)
If Not selected Then selected = model.Extension.SelectByID2("Front Plane", "PLANE", 0, 0, 0, False, 0, Nothing, 0)
If Not selected Then Err.Raise vbObjectError + 3, , "Could not select Front Plane for feature_2_path."
sketchManager.InsertSketch True
WScript.Sleep 200
If sketchManager.ActiveSketch Is Nothing Then
  model.InsertSketch2 True
  WScript.Sleep 300
End If
Set segment = sketchManager.CreateLine(0, 0, 0, 0.01, 0, 0)
logFile.WriteLine "probe_line=" & (Not segment Is Nothing)
If segment Is Nothing And sketchManager.ActiveSketch Is Nothing Then
  Err.Raise vbObjectError + 8, , "SolidWorks did not enter sketch mode for feature_2_path."
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
logFile.WriteLine "feature_2_path_outer_points=62"
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.014568012179609915, 0, 0, -0.014545386979876767, 0.0027118586983112232, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.014545386979876767, 0.0027118586983112232, 0, -0.014462840210700432, 0.0045163040745011106, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.014462840210700432, 0.0045163040745011106, 0, -0.014323088290669802, 0.0063158584719702794, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.014323088290669802, 0.0063158584719702794, 0, -0.014097805111274222, 0.0081044377285573576, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.014097805111274222, 0.0081044377285573576, 0, -0.013941107210591981, 0.0089914904493613081, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.013941107210591981, 0.0089914904493613081, 0, -0.013767958464178144, 0.0098755153489153286, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.013767958464178144, 0.0098755153489153286, 0, -0.013330315709879323, 0.011620759545124971, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.013330315709879323, 0.011620759545124971, 0, -0.013056406320782995, 0.012478020150612661, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.013056406320782995, 0.012478020150612661, 0, -0.012420859881666798, 0.014158270657090783, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.012420859881666798, 0.014158270657090783, 0, -0.011617925309494521, 0.015764008473799648, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.011617925309494521, 0.015764008473799648, 0, -0.011177917074711313, 0.016546829627163532, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.011177917074711313, 0.016546829627163532, 0, -0.010677432675738332, 0.017291974771267208, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.010677432675738332, 0.017291974771267208, 0, -0.0095771534977218166, 0.018705882271504617, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.0095771534977218166, 0.018705882271504617, 0, -0.0089688796014804339, 0.019364268665416198, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.0089688796014804339, 0.019364268665416198, 0, -0.0083212865058541041, 0.019982993771789911, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.0083212865058541041, 0.019982993771789911, 0, -0.0076381592162850943, 0.02056132192845337, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.0076381592162850943, 0.02056132192845337, 0, -0.0069240100013712091, 0.021100310402899624, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.0069240100013712091, 0.021100310402899624, 0, -0.0061742875432168297, 0.021589326315213649, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.0061742875432168297, 0.021589326315213649, 0, -0.0053896972623221281, 0.022018741828633032, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.0053896972623221281, 0.022018741828633032, 0, -0.0045806036641717045, 0.022398226924790182, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.0045806036641717045, 0.022398226924790182, 0, -0.0037483802805794646, 0.022724235891235872, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.0037483802805794646, 0.022724235891235872, 0, -0.0028945732811012895, 0.022987560615602427, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.0028945732811012895, 0.022987560615602427, 0, -0.002023435807742298, 0.023186079038599972, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.002023435807742298, 0.023186079038599972, 0, -0.0011406367042834464, 0.02331955160535604, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.0011406367042834464, 0.02331955160535604, 0, -0.00025018664197711606, 0.023381183590616174, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.00025018664197711606, 0.023381183590616174, 0, 0.00064162062409798735, 0.02337615532386314, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.00064162062409798735, 0.02337615532386314, 0, 0.0015302441318697443, 0.023302742719545421, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0015302441318697443, 0.023302742719545421, 0, 0.0024091923836094121, 0.023151739807929943, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0024091923836094121, 0.023151739807929943, 0, 0.0032715424184665332, 0.022923838619071817, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0032715424184665332, 0.022923838619071817, 0, 0.0041155908086821192, 0.022638933417089287, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0041155908086821192, 0.022638933417089287, 0, 0.0049276367101456298, 0.022272491863636289, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0049276367101456298, 0.022272491863636289, 0, 0.0057079082077606935, 0.021843578612910249, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0057079082077606935, 0.021843578612910249, 0, 0.006444786383632552, 0.02134320172930795, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.006444786383632552, 0.02134320172930795, 0, 0.0071345370407334919, 0.020780471901392532, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0071345370407334919, 0.020780471901392532, 0, 0.0077695675602140425, 0.02015782495415349, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0077695675602140425, 0.02015782495415349, 0, 0.0083416558389971477, 0.019474506462240918, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0083416558389971477, 0.019474506462240918, 0, 0.0092709125241461094, 0.017958826992883672, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0092709125241461094, 0.017958826992883672, 0, 0.0096255143603154077, 0.017142455376056877, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0096255143603154077, 0.017142455376056877, 0, 0.0098991334914699993, 0.016297416573407619, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0098991334914699993, 0.016297416573407619, 0, 0.010084015472371439, 0.015428025750478736, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.010084015472371439, 0.015428025750478736, 0, 0.010180611510716519, 0.014544721245082562, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.010180611510716519, 0.014544721245082562, 0, 0.010185544215082483, 0.013656080509293627, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.010185544215082483, 0.013656080509293627, 0, 0.010095428563376155, 0.012772619469402507, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.010095428563376155, 0.012772619469402507, 0, 0.0099122950577035622, 0.011903263410297031, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0099122950577035622, 0.011903263410297031, 0, 0.0096301501237009354, 0.011061651376817718, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0096301501237009354, 0.011061651376817718, 0, 0.0092728031760832743, 0.010249028105499266, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0092728031760832743, 0.010249028105499266, 0, 0.0088220646460758639, 0.0094839518036218297, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0088220646460758639, 0.0094839518036218297, 0, 0.0082889212180098457, 0.0087753298355193066, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0082889212180098457, 0.0087753298355193066, 0, 0.0076786375142495651, 0.0081311183222258741, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0076786375142495651, 0.0081311183222258741, 0, 0.0069950740924373412, 0.0075659143853604987, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0069950740924373412, 0.0075659143853604987, 0, 0.0062580908146720095, 0.0070740053886852372, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0062580908146720095, 0.0070740053886852372, 0, 0.0054646005958689211, 0.0066787356375416001, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0054646005958689211, 0.0066787356375416001, 0, 0.0046312012404017815, 0.0063798961859545108, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0046312012404017815, 0.0063798961859545108, 0, 0.0037692339313914265, 0.0061776690695358625, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0037692339313914265, 0.0061776690695358625, 0, 0.0028890648374749871, 0.0060842302179592266, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0028890648374749871, 0.0060842302179592266, 0, 0.0020044991739521585, 0.0061035659162511158, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0020044991739521585, 0.0061035659162511158, 0, 0.0011278544461250496, 0.0062307498032452401, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0011278544461250496, 0.0062307498032452401, 0, 0.00027171860190022845, 0.0064506243554409946, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.00027171860190022845, 0.0064506243554409946, 0, -0.00054788396243560559, 0.0067836095735894619, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.00054788396243560559, 0.0067836095735894619, 0, -0.0013214187098222749, 0.0072264925617751769, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.0013214187098222749, 0.0072264925617751769, 0, -0.0020822875192970862, 0.007790015698378415, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
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
If planeFeature Is Nothing Then Err.Raise vbObjectError + 10, , "Could not find feature_2_path."
planeFeature.Name = "CADView Sweep Path"
logFile.WriteLine "sketch_ok=feature_2_path"
logFile.WriteLine "sketch_start=feature_2_profile"
model.ClearSelection2 True
selected = False
Set planeFeature = partDoc.FeatureByName("Top Plane")
If Not planeFeature Is Nothing Then selected = planeFeature.Select2(False, 0)
If Not selected Then selected = model.Extension.SelectByID2("Top Plane", "PLANE", 0, 0, 0, False, 0, Nothing, 0)
If Not selected Then Err.Raise vbObjectError + 3, , "Could not select Top Plane for feature_2_profile."
sketchManager.InsertSketch True
WScript.Sleep 200
If sketchManager.ActiveSketch Is Nothing Then
  model.InsertSketch2 True
  WScript.Sleep 300
End If
Set segment = sketchManager.CreateLine(0, 0, 0, 0.01, 0, 0)
logFile.WriteLine "probe_line=" & (Not segment Is Nothing)
If segment Is Nothing And sketchManager.ActiveSketch Is Nothing Then
  Err.Raise vbObjectError + 8, , "SolidWorks did not enter sketch mode for feature_2_profile."
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
logFile.WriteLine "feature_2_profile_outer_points=9"
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.014731369192435381, -0.00078466039915327593, 0, -0.014731369192435381, 0.00078466039915327539, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.014731369192435381, 0.00078466039915327539, 0, -0.014689866362348951, 0.0005884952993649564, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.014689866362348951, 0.0005884952993649564, 0, -0.01451609587611429, 0.00039233019957663742, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.01451609587611429, 0.00039233019957663742, 0, -0.014429845005306263, 0.00019616509978831898, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.014429845005306263, 0.00019616509978831898, 0, -0.014404655166784453, 0, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.014404655166784453, 0, 0, -0.014430552949029406, -0.00019616509978831898, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.014430552949029406, -0.00019616509978831898, 0, -0.01451687359546955, -0.00039233019957663796, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.01451687359546955, -0.00039233019957663796, 0, -0.014692417782225371, -0.00058849529936495695, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.014692417782225371, -0.00058849529936495695, 0, -0.014731369192435381, -0.00078466039915327593, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
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
If planeFeature Is Nothing Then Err.Raise vbObjectError + 10, , "Could not find feature_2_profile."
planeFeature.Name = "CADView Sweep Profile"
logFile.WriteLine "sketch_ok=feature_2_profile"
model.ClearSelection2 True
selected = model.Extension.SelectByID2("CADView Sweep Profile", "SKETCH", 0, 0, 0, False, 1, Nothing, 0)
If Not selected Then Err.Raise vbObjectError + 11, , "Could not select sweep profile."
selected = model.Extension.SelectByID2("CADView Sweep Path", "SKETCH", 0, 0, 0, True, 4, Nothing, 0)
If Not selected Then Err.Raise vbObjectError + 12, , "Could not select sweep path."
Set feature = model.FeatureManager.InsertCutSwept5(False, False, 0, True, True, 0, 0, False, 0, 0, 0, 0, True, True, 0, True, False, True, False, False, 0, 0)
fallbackUsed = False
If feature Is Nothing Then
fallbackUsed = True
logFile.WriteLine "feature_fallback=2:sweep_cut_to_cut"
logFile.WriteLine "sketch_start=feature_2_fallback_profile"
model.ClearSelection2 True
selected = False
Set planeFeature = partDoc.FeatureByName("Front Plane")
If Not planeFeature Is Nothing Then selected = planeFeature.Select2(False, 0)
If Not selected Then selected = model.Extension.SelectByID2("Front Plane", "PLANE", 0, 0, 0, False, 0, Nothing, 0)
If Not selected Then Err.Raise vbObjectError + 3, , "Could not select Front Plane for feature_2_fallback_profile."
sketchManager.InsertSketch True
WScript.Sleep 200
If sketchManager.ActiveSketch Is Nothing Then
  model.InsertSketch2 True
  WScript.Sleep 300
End If
Set segment = sketchManager.CreateLine(0, 0, 0, 0.01, 0, 0)
logFile.WriteLine "probe_line=" & (Not segment Is Nothing)
If segment Is Nothing And sketchManager.ActiveSketch Is Nothing Then
  Err.Raise vbObjectError + 8, , "SolidWorks did not enter sketch mode for feature_2_fallback_profile."
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
logFile.WriteLine "feature_2_fallback_profile_outer_points=121"
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.010603020749225853, 0.017695773816552698, 0, -0.0098667140562085972, 0.018633116203780702, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.0098667140562085972, 0.018633116203780702, 0, -0.0089366205022227314, 0.019639783075421052, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.0089366205022227314, 0.019639783075421052, 0, -0.0080957649768528799, 0.020411818427487766, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.0080957649768528799, 0.020411818427487766, 0, -0.0071574102641859573, 0.021143035223062299, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.0071574102641859573, 0.021143035223062299, 0, -0.0061780479694849904, 0.021781769759501302, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.0061780479694849904, 0.021781769759501302, 0, -0.0051490962268214528, 0.022332891159709, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.0051490962268214528, 0.022332891159709, 0, -0.0041059575713080455, 0.022778757176376549, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.0041059575713080455, 0.022778757176376549, 0, -0.003108272568073825, 0.023106289886996687, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.003108272568073825, 0.023106289886996687, 0, -0.0018789827824024408, 0.023386417578880988, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.0018789827824024408, 0.023386417578880988, 0, -0.0008837401755548449, 0.023518351999744488, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.0008837401755548449, 0.023518351999744488, 0, 0.00019380088568887022, 0.023563122304212945, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.00019380088568887022, 0.023563122304212945, 0, 0.0012588576928248365, 0.02350749521309578, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0012588576928248365, 0.02350749521309578, 0, 0.0022497638994121221, 0.023362613451760526, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0022497638994121221, 0.023362613451760526, 0, 0.0036843204771666205, 0.022983644902790371, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0036843204771666205, 0.022983644902790371, 0, 0.0046048032638970893, 0.02262245009660831, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0046048032638970893, 0.02262245009660831, 0, 0.0055798724420898808, 0.022120368795183112, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0055798724420898808, 0.022120368795183112, 0, 0.0063673776295947275, 0.021612943058940667, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0063673776295947275, 0.021612943058940667, 0, 0.0071537901245575727, 0.020989465058218429, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0071537901245575727, 0.020989465058218429, 0, 0.0078670538429849411, 0.020295647324018371, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0078670538429849411, 0.020295647324018371, 0, 0.008502101452407167, 0.019537028860646781, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.008502101452407167, 0.019537028860646781, 0, 0.0093000843484639904, 0.01828334876905361, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0093000843484639904, 0.01828334876905361, 0, 0.0097083292576322835, 0.017405716614947005, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0097083292576322835, 0.017405716614947005, 0, 0.010028405008652834, 0.016465661248360249, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.010028405008652834, 0.016465661248360249, 0, 0.010231995495211251, 0.015566735582019153, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.010231995495211251, 0.015566735582019153, 0, 0.010343005976788141, 0.014625895572848557, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.010343005976788141, 0.014625895572848557, 0, 0.010352279483851288, 0.01368477259937065, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.010352279483851288, 0.01368477259937065, 0, 0.010264651364997093, 0.012785738632118659, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.010264651364997093, 0.012785738632118659, 0, 0.010087386402877273, 0.011915686378943389, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.010087386402877273, 0.011915686378943389, 0, 0.0098424078087326547, 0.01114108957995324, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0098424078087326547, 0.01114108957995324, 0, 0.0094403626242633154, 0.010212331036098667, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0094403626242633154, 0.010212331036098667, 0, 0.0089717625089997272, 0.0094117399877182845, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0089717625089997272, 0.0094117399877182845, 0, 0.0084258007752355379, 0.0086827021067157027, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0084258007752355379, 0.0086827021067157027, 0, 0.0078039133724025619, 0.008023165742957878, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0078039133724025619, 0.008023165742957878, 0, 0.0070332003030134519, 0.0073857512953488238, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0070332003030134519, 0.0073857512953488238, 0, 0.0063820550627099858, 0.0069542666236389432, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0063820550627099858, 0.0069542666236389432, 0, 0.0056266964571843438, 0.006565733167573337, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0056266964571843438, 0.006565733167573337, 0, 0.0048183037954213021, 0.006258607750608481, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0048183037954213021, 0.006258607750608481, 0, 0.0039125653328124432, 0.0060310102673528229, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0039125653328124432, 0.0060310102673528229, 0, 0.0030323550743356787, 0.0059215955383578479, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0030323550743356787, 0.0059215955383578479, 0, 0.0021492596258059029, 0.0059178743639879388, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0021492596258059029, 0.0059178743639879388, 0, 0.00088016666437320894, 0.0061018601279562218, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.00088016666437320894, 0.0061018601279562218, 0, 0.00011480966149006023, 0.006326575438560033, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.00011480966149006023, 0.006326575438560033, 0, -0.00062609244264671255, 0.006639550089086981, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.00062609244264671255, 0.006639550089086981, 0, -0.0013775865837277333, 0.007065699196514303, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.0013775865837277333, 0.007065699196514303, 0, -0.0020835388966346782, 0.0075912250151642362, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.0020835388966346782, 0.0075912250151642362, 0, -0.0026926703711281147, 0.0081750278437120235, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.0026926703711281147, 0.0081750278437120235, 0, -0.012193630188664432, -0.0018571840176376669, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.012193630188664432, -0.0018571840176376669, 0, -0.0024701085472722032, 0.0084242376493762813, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.0024701085472722032, 0.0084242376493762813, 0, -0.0015285875184328939, 0.0075700317295541329, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.0015285875184328939, 0.0075700317295541329, 0, -0.00094051621025475996, 0.0071823681564937309, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.00094051621025475996, 0.0071823681564937309, 0, -0.0003016948698363873, 0.0068514064595679349, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.0003016948698363873, 0.0068514064595679349, 0, 0.0006531203091059639, 0.0065005930920478709, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0006531203091059639, 0.0065005930920478709, 0, 0.0017286892022626932, 0.0062835117765206077, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0017286892022626932, 0.0062835117765206077, 0, 0.0024545589251071154, 0.0062358166845535076, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0024545589251071154, 0.0062358166845535076, 0, 0.0031812606530248954, 0.0062640581240068129, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0031812606530248954, 0.0062640581240068129, 0, 0.0039135895050992154, 0.0063681609805719235, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0039135895050992154, 0.0063681609805719235, 0, 0.0046365030134040983, 0.0065473213908255603, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0046365030134040983, 0.0065473213908255603, 0, 0.0056887598496640377, 0.0069564590053039265, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0056887598496640377, 0.0069564590053039265, 0, 0.006659172050759503, 0.0075199826203770021, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.006659172050759503, 0.0075199826203770021, 0, 0.0072563599056120085, 0.007976657479038007, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0072563599056120085, 0.007976657479038007, 0, 0.0080770244486511582, 0.008784002698625136, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0080770244486511582, 0.008784002698625136, 0, 0.0087761120657793516, 0.0097142146041757152, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0087761120657793516, 0.0097142146041757152, 0, 0.0091601320073996413, 0.010386419635170754, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0091601320073996413, 0.010386419635170754, 0, 0.0094744917604736561, 0.011091128684111788, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0094744917604736561, 0.011091128684111788, 0, 0.0097220200115165668, 0.011831672199823669, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0097220200115165668, 0.011831672199823669, 0, 0.0098998127880008339, 0.012603257095028164, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0098998127880008339, 0.012603257095028164, 0, 0.010027065191982243, 0.013798049513909066, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.010027065191982243, 0.013798049513909066, 0, 0.010015025079784612, 0.014597791880578592, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.010015025079784612, 0.014597791880578592, 0, 0.0098540000469221622, 0.01578712467494282, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0098540000469221622, 0.01578712467494282, 0, 0.0096516345365023747, 0.016575700385061978, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0096516345365023747, 0.016575700385061978, 0, 0.0093739264230950515, 0.017351046501393068, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0093739264230950515, 0.017351046501393068, 0, 0.0090232144966540511, 0.018102178303895215, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0090232144966540511, 0.018102178303895215, 0, 0.0086037429952609545, 0.018817751286912175, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0086037429952609545, 0.018817751286912175, 0, 0.0081144160588100239, 0.019499284281396315, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0081144160588100239, 0.019499284281396315, 0, 0.0072642548232590715, 0.020438328647139452, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0072642548232590715, 0.020438328647139452, 0, 0.0066226258393202392, 0.021005154460620384, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0066226258393202392, 0.021005154460620384, 0, 0.0059287233445581124, 0.021515682140379178, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0059287233445581124, 0.021515682140379178, 0, 0.0048072494692038602, 0.022162450834013095, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0048072494692038602, 0.022162450834013095, 0, 0.0040065636404620639, 0.022514855347641152, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0040065636404620639, 0.022514855347641152, 0, 0.0031669331476586789, 0.022801517401233453, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0031669331476586789, 0.022801517401233453, 0, 0.0022948536868524802, 0.023018279061900238, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0022948536868524802, 0.023018279061900238, 0, 0.0014044756744555668, 0.023160317845412094, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.0014044756744555668, 0.023160317845412094, 0, 0.00050260807670320421, 0.023227197380006379, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(0.00050260807670320421, 0.023227197380006379, 0, -0.00041470346100429012, 0.023219566676594781, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.00041470346100429012, 0.023219566676594781, 0, -0.0013421392665181663, 0.023136145595167926, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.0013421392665181663, 0.023136145595167926, 0, -0.0022705054163481495, 0.022976199256501253, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.0022705054163481495, 0.022976199256501253, 0, -0.0031899843796057647, 0.022740202675820456, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.0031899843796057647, 0.022740202675820456, 0, -0.0040941123682028306, 0.022430218686678566, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.0040941123682028306, 0.022430218686678566, 0, -0.0049873196075680293, 0.022044496666903782, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.0049873196075680293, 0.022044496666903782, 0, -0.00586271788353151, 0.021584263618222507, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.00586271788353151, 0.021584263618222507, 0, -0.0067120159550491517, 0.021052082014536153, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.0067120159550491517, 0.021052082014536153, 0, -0.0074740751179794233, 0.02049401703661876, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.0074740751179794233, 0.02049401703661876, 0, -0.0082585623588466613, 0.019829775968133685, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.0082585623588466613, 0.019829775968133685, 0, -0.0090087724041289681, 0.019096557824768837, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.0090087724041289681, 0.019096557824768837, 0, -0.0097193535446565109, 0.018297229112796218, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.0097193535446565109, 0.018297229112796218, 0, -0.010383526437497344, 0.017436982190785745, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.010383526437497344, 0.017436982190785745, 0, -0.010997053747310833, 0.016520876900669796, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.010997053747310833, 0.016520876900669796, 0, -0.011565042333649692, 0.015540554754832228, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.011565042333649692, 0.015540554754832228, 0, -0.012086355064174466, 0.014494448245156211, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.012086355064174466, 0.014494448245156211, 0, -0.012558723642897092, 0.013382432674144625, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.012558723642897092, 0.013382432674144625, 0, -0.012990158029988668, 0.012172171803754435, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.012990158029988668, 0.012172171803754435, 0, -0.013354388422043834, 0.01093048416461998, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.013354388422043834, 0.01093048416461998, 0, -0.013660932658453582, 0.0096280750103041029, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.013660932658453582, 0.0096280750103041029, 0, -0.01391160946982555, 0.0082626126527135472, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.01391160946982555, 0.0082626126527135472, 0, -0.01411327884630907, 0.0067820316142246911, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.01411327884630907, 0.0067820316142246911, 0, -0.014357895050477652, 0.0034724575483331623, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.014357895050477652, 0.0034724575483331623, 0, -0.014405326933650577, -0.00022598901671882921, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.014405326933650577, -0.00022598901671882921, 0, -0.012425172053820911, -0.0021016726893752758, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.012425172053820911, -0.0021016726893752758, 0, -0.014659380116952513, -0.0044608078780434164, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.014659380116952513, -0.0044608078780434164, 0, -0.014737756643026205, 0.00039505482958423246, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.014737756643026205, 0.00039505482958423246, 0, -0.014706066360585088, 0.0029248374486365537, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.014706066360585088, 0.0029248374486365537, 0, -0.014598510048991424, 0.0050732043471109047, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.014598510048991424, 0.0050732043471109047, 0, -0.014448125852961935, 0.0067504037403766362, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.014448125852961935, 0.0067504037403766362, 0, -0.014219247163917299, 0.0084213729812907586, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.014219247163917299, 0.0084213729812907586, 0, -0.013873475296993001, 0.010186424490309466, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.013873475296993001, 0.010186424490309466, 0, -0.013539941342076036, 0.011501264751420159, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.013539941342076036, 0.011501264751420159, 0, -0.013093836163746913, 0.012897584243516093, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.013093836163746913, 0.012897584243516093, 0, -0.012580769057132568, 0.014202100216322287, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.012580769057132568, 0.014202100216322287, 0, -0.012033376203000568, 0.015358462627681403, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.012033376203000568, 0.015358462627681403, 0, -0.011316671451889783, 0.01663304294662795, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
segmentIndex = segmentIndex + 1
Set segment = sketchManager.CreateLine(-0.011316671451889783, 0.01663304294662795, 0, -0.010603020749225853, 0.017695773816552698, 0)
If Not segment Is Nothing Then createdCount = createdCount + 1
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
If planeFeature Is Nothing Then Err.Raise vbObjectError + 10, , "Could not find feature_2_fallback_profile."
planeFeature.Name = "CADView Sweep Fallback Cut"
logFile.WriteLine "sketch_ok=feature_2_fallback_profile"
Set feature = model.FeatureManager.FeatureCut3(True, False, False, 6, 0, 0.0015693207983065514, 0, False, False, False, False, 0, 0, False, False, False, False, False, True, True, True, True, False, 0, 0, False)
If feature Is Nothing Then Err.Raise vbObjectError + 13, , "SolidWorks rejected both the recovered Sweep-Cut and its native Cut-Extrude fallback."
feature.Name = "CADView Perimeter Groove Cut"
logFile.WriteLine "feature_ok=2:cut_fallback"
End If
If Not fallbackUsed Then
feature.Name = "CADView Perimeter Sweep Cut"
logFile.WriteLine "feature_ok=2:sweep_cut"
End If
model.EditRebuild3
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
MsgBox "Editable SolidWorks part is open in SolidWorks with 2 native features." & vbCrLf & vbCrLf & "Saved as:" & vbCrLf & outputFile & vbCrLf & vbCrLf & "Do not double-click the file from Explorer while SolidWorks still has it open.", vbInformation, "CAD-View"
