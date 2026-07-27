using System.Runtime.InteropServices;
using System.Text.Json;
using System.Text.Json.Serialization;
using SolidWorks.Interop.sldworks;

internal static class Program
{
    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNameCaseInsensitive = true,
    };

    [STAThread]
    private static int Main(string[] args)
    {
        if (args.Length < 2)
        {
            Console.Error.WriteLine(
                "Usage: CadView.SolidWorksBridge <recipe.json> <output.SLDPRT> [--visible]"
            );
            return 2;
        }

        try
        {
            var recipe = JsonSerializer.Deserialize<Recipe>(
                File.ReadAllText(args[0]),
                JsonOptions
            ) ?? throw new InvalidOperationException("Recipe JSON is empty.");
            Build(recipe, Path.GetFullPath(args[1]), args.Contains("--visible"));
            Console.WriteLine(
                JsonSerializer.Serialize(new { status = "ok", output = Path.GetFullPath(args[1]) })
            );
            return 0;
        }
        catch (Exception exception)
        {
            Console.Error.WriteLine(
                JsonSerializer.Serialize(
                    new
                    {
                        status = "error",
                        error = exception.Message,
                        type = exception.GetType().Name,
                    }
                )
            );
            return 1;
        }
    }

    private static void Build(Recipe recipe, string outputPath, bool visible)
    {
        if (
            recipe.Features.Count == 0
            || recipe.Features.Any(
                feature => feature.Type is not ("extrude" or "cut" or "sweep_cut")
            )
        )
        {
            throw new InvalidOperationException(
                "The bridge requires native extrude/cut/sweep features."
            );
        }

        var scale = recipe.Unit switch
        {
            "mm" => 0.001,
            "cm" => 0.01,
            "m" => 1.0,
            "in" => 0.0254,
            _ => throw new InvalidOperationException($"Unsupported unit: {recipe.Unit}"),
        };

        var application = new SldWorksClass();
        ModelDoc2? model = null;
        try
        {
            // SketchManager silently ignores InsertSketch on hidden documents.
            // Keep both the application and part document visible while native
            // sketch features are being authored.
            application.Visible = true;
            application.UserControl = true;
            WaitForReady(application);
            const int swDocPart = 1;
            application.DocumentVisible(true, swDocPart);
            const int swDefaultTemplatePart = 8;
            var template = application.GetUserPreferenceStringValue(
                swDefaultTemplatePart
            );
            if (string.IsNullOrWhiteSpace(template))
            {
                throw new InvalidOperationException(
                    "SolidWorks has no default part template configured."
                );
            }
            model = (ModelDoc2?)application.NewDocument(template, 0, 0, 0);
            if (model is null)
            {
                throw new InvalidOperationException("SolidWorks could not create a part.");
            }
            application.DocumentVisible(true, swDocPart);
            model.Visible = true;
            var activationErrors = 0;
            application.ActivateDoc3(model.GetTitle(), true, 0, ref activationErrors);
            if (activationErrors != 0)
            {
                throw new InvalidOperationException(
                    $"SolidWorks could not activate the new part (error={activationErrors})."
                );
            }

            foreach (var sourceFeature in recipe.Features)
            {
                if (sourceFeature.Type == "sweep_cut")
                {
                    if (sourceFeature.Path is null || sourceFeature.Profile is null)
                    {
                        throw new InvalidOperationException(
                            "Sweep-Cut recipe is missing its profile or path."
                        );
                    }
                    var pathSketch = CreateSketch(
                        model,
                        new SketchRecipe(
                            sourceFeature.Path.Name,
                            sourceFeature.Path.Plane,
                            new LoopRecipe(
                                "polyline",
                                sourceFeature.Path.Points,
                                null,
                                null
                            ),
                            []
                        ),
                        scale,
                        closed: sourceFeature.Path.Closed
                    );
                    pathSketch.Name = sourceFeature.Path.Name;
                    var profileSketch = CreateSketch(
                        model,
                        sourceFeature.Profile,
                        scale
                    );
                    profileSketch.Name = sourceFeature.Profile.Name;
                    model.ClearSelection2(true);
                    var profileSelected = profileSketch.Select2(false, 1);
                    var pathSelected = pathSketch.Select2(true, 4);
                    if (!profileSelected || !pathSelected)
                    {
                        throw new InvalidOperationException(
                            "SolidWorks could not select the Sweep-Cut profile/path."
                        );
                    }
                    var sweep = model.FeatureManager.InsertCutSwept5(
                        false,
                        false,
                        0,
                        true,
                        true,
                        0,
                        0,
                        false,
                        0,
                        0,
                        0,
                        0,
                        true,
                        true,
                        0,
                        true,
                        false,
                        true,
                        false,
                        false,
                        0,
                        0
                    );
                    if (sweep is null)
                    {
                        throw new InvalidOperationException(
                            "SolidWorks rejected the recovered Sweep-Cut."
                        );
                    }
                    sweep.Name = sourceFeature.Name;
                    model.EditRebuild3();
                    continue;
                }

                var sketchRecipe = sourceFeature.Sketch
                    ?? throw new InvalidOperationException(
                        $"{sourceFeature.Name} is missing its sketch."
                    );
                var sketchFeature = CreateSketch(model, sketchRecipe, scale);
                var startCondition = Math.Abs(sourceFeature.StartOffset) > 1e-12
                    ? 3
                    : 0;
                Feature? feature = sourceFeature.Type == "cut"
                    ? model.FeatureManager.FeatureCut3(
                        true,
                        false,
                        false,
                        0,
                        0,
                        sourceFeature.Depth * scale,
                        0,
                        false,
                        false,
                        false,
                        false,
                        0,
                        0,
                        false,
                        false,
                        false,
                        false,
                        false,
                        true,
                        true,
                        true,
                        true,
                        false,
                        startCondition,
                        sourceFeature.StartOffset * scale,
                        false
                    )
                    : model.FeatureManager.FeatureExtrusion3(
                        true,
                        false,
                        false,
                        sourceFeature.EndCondition == "midplane" ? 6 : 0,
                        0,
                        sourceFeature.Depth * scale,
                        0,
                        false,
                        false,
                        false,
                        true,
                        0,
                        0,
                        false,
                        false,
                        false,
                        false,
                        true,
                        false,
                        true,
                        startCondition,
                        sourceFeature.StartOffset * scale,
                        false
                    );
                if (feature is null)
                {
                    var sketch = (Sketch)sketchFeature.GetSpecificFeature2();
                    var segments = (object[]?)sketch.GetSketchSegments();
                    throw new InvalidOperationException(
                        $"SolidWorks rejected '{sourceFeature.Name}' "
                            + $"({segments?.Length ?? 0} sketch segments were created)."
                    );
                }
                sketchFeature.Name = sketchRecipe.Name;
                feature.Name = sourceFeature.Name;
                model.EditRebuild3();
            }

            Directory.CreateDirectory(
                Path.GetDirectoryName(outputPath)
                    ?? throw new InvalidOperationException("Output directory is invalid.")
            );
            var errors = 0;
            var warnings = 0;
            var saved = model.Extension.SaveAs(
                outputPath,
                0,
                2,
                null,
                ref errors,
                ref warnings
            );
            if (!saved || !File.Exists(outputPath))
            {
                throw new InvalidOperationException(
                    $"SolidWorks SaveAs failed (errors={errors}, warnings={warnings})."
                );
            }
        }
        finally
        {
            if (model is not null && !visible)
            {
                application.CloseDoc(model.GetTitle());
            }
            if (model is not null)
            {
                Marshal.FinalReleaseComObject(model);
            }
            Marshal.FinalReleaseComObject(application);
        }
    }

    private static void WaitForReady(SldWorksClass application)
    {
        var ready = false;
        DSldWorksEvents_OnIdleNotifyEventHandler onIdle = () =>
        {
            ready = true;
            return 0;
        };
        application.OnIdleNotify += onIdle;
        try
        {
            var deadline = DateTime.UtcNow.AddSeconds(60);
            while (!ready && DateTime.UtcNow < deadline)
            {
                Thread.Sleep(100);
            }
            if (!ready)
            {
                throw new TimeoutException(
                    "SolidWorks did not reach an idle/ready state within 60 seconds."
                );
            }
        }
        finally
        {
            application.OnIdleNotify -= onIdle;
        }
    }

    private static Feature CreateSketch(
        ModelDoc2 model,
        SketchRecipe sketch,
        double scale,
        bool closed = true
    )
    {
        var part = (PartDoc)model;
        model.ClearSelection2(true);
        var planeFeature = (Feature?)part.FeatureByName(sketch.Plane);
        var selected = planeFeature?.Select2(false, 0) ?? false;
        if (!selected)
        {
            selected = model.Extension.SelectByID2(
                sketch.Plane,
                "PLANE",
                0,
                0,
                0,
                false,
                0,
                null,
                0
            );
        }
        if (!selected)
        {
            throw new InvalidOperationException(
                $"SolidWorks could not select '{sketch.Plane}'. "
                    + "The part template may use localized plane names."
            );
        }

        var manager = model.SketchManager;
        manager.InsertSketch(true);
        Thread.Sleep(200);
        if (manager.ActiveSketch is null)
        {
            model.ClearSelection2(true);
            planeFeature = (Feature?)part.FeatureByName(sketch.Plane);
            selected = planeFeature?.Select2(false, 0) ?? false;
            if (!selected)
            {
                selected = model.Extension.SelectByID2(
                    sketch.Plane,
                    "PLANE",
                    0,
                    0,
                    0,
                    false,
                    0,
                    null,
                    0
                );
            }
            model.InsertSketch2(true);
            Thread.Sleep(300);
        }
        var probe = manager.CreateLine(0, 0, 0, 0.01, 0, 0);
        if (probe is null && manager.ActiveSketch is null)
        {
            throw new InvalidOperationException(
                $"SolidWorks did not enter sketch mode on '{sketch.Plane}'."
            );
        }
        if (probe is not null)
        {
            probe.Select4(false, null);
            model.EditDelete();
        }
        model.SetAddToDB(true);
        model.SetDisplayWhenAdded(false);
        manager.AddToDB = true;
        manager.DisplayWhenAdded = false;
        model.ViewZoomtofit2();

        CreateSpline(
            manager,
            sketch.OuterLoop.Points
                ?? throw new InvalidOperationException("Outer loop has no points."),
            scale,
            closed
        );
        foreach (var loop in sketch.InnerLoops)
        {
            if (loop.Kind == "circle")
            {
                if (loop.Center is null || loop.Center.Length != 2 || loop.Radius is null)
                {
                    throw new InvalidOperationException("Circle loop is incomplete.");
                }
                var circle = manager.CreateCircleByRadius(
                    loop.Center[0] * scale,
                    loop.Center[1] * scale,
                    0,
                    loop.Radius.Value * scale
                );
                if (circle is null)
                {
                    throw new InvalidOperationException(
                        "SolidWorks could not create the through-hole circle."
                    );
                }
            }
            else
            {
                CreateSpline(
                    manager,
                    loop.Points
                        ?? throw new InvalidOperationException("Polyline loop has no points."),
                    scale,
                    true
                );
            }
        }
        model.SetAddToDB(false);
        model.SetDisplayWhenAdded(true);
        manager.AddToDB = false;
        manager.DisplayWhenAdded = true;
        model.ViewZoomtofit2();
        manager.InsertSketch(true);

        Feature? sketchFeature = null;
        for (var index = 1; index < 100; index++)
        {
            sketchFeature = (Feature?)part.FeatureByName($"Sketch{index}") ?? sketchFeature;
        }
        if (sketchFeature is null)
        {
            throw new InvalidOperationException("Recovered sketch was not created.");
        }
        return sketchFeature;
    }

    private static void CreateSpline(
        SketchManager manager,
        IReadOnlyList<double[]> points,
        double scale,
        bool closed
    )
    {
        var minimum = closed ? 3 : 2;
        if (points.Count < minimum)
        {
            throw new InvalidOperationException(
                $"Sketch curve has fewer than {minimum} points."
            );
        }

        var pointCount = points.Count + (closed ? 1 : 0);
        var coordinates = new double[pointCount * 3];
        for (var index = 0; index < pointCount; index++)
        {
            var point = points[index % points.Count];
            coordinates[index * 3] = point[0] * scale;
            coordinates[index * 3 + 1] = point[1] * scale;
            coordinates[index * 3 + 2] = 0;
        }

        var segment = manager.CreateSpline2(coordinates, true);
        if (segment is null)
        {
            throw new InvalidOperationException(
                "SolidWorks could not create the recovered sketch spline."
            );
        }
    }
}

internal sealed record Recipe(
    [property: JsonPropertyName("unit")] string Unit,
    [property: JsonPropertyName("features")] List<FeatureRecipe> Features
);

internal sealed record FeatureRecipe(
    [property: JsonPropertyName("name")] string Name,
    [property: JsonPropertyName("type")] string Type,
    [property: JsonPropertyName("depth")] double Depth,
    [property: JsonPropertyName("start_offset")] double StartOffset,
    [property: JsonPropertyName("end_condition")] string? EndCondition,
    [property: JsonPropertyName("sketch")] SketchRecipe? Sketch,
    [property: JsonPropertyName("profile")] SketchRecipe? Profile,
    [property: JsonPropertyName("path")] PathRecipe? Path
);

internal sealed record PathRecipe(
    [property: JsonPropertyName("name")] string Name,
    [property: JsonPropertyName("plane")] string Plane,
    [property: JsonPropertyName("points")] double[][] Points,
    [property: JsonPropertyName("closed")] bool Closed
);

internal sealed record SketchRecipe(
    [property: JsonPropertyName("name")] string Name,
    [property: JsonPropertyName("plane")] string Plane,
    [property: JsonPropertyName("outer_loop")] LoopRecipe OuterLoop,
    [property: JsonPropertyName("inner_loops")] List<LoopRecipe> InnerLoops
);

internal sealed record LoopRecipe(
    [property: JsonPropertyName("kind")] string Kind,
    [property: JsonPropertyName("points")] double[][]? Points,
    [property: JsonPropertyName("center")] double[]? Center,
    [property: JsonPropertyName("radius")] double? Radius
);
