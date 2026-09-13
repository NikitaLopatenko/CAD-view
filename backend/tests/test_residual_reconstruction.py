import trimesh

from parametric_reconstruction import (
    build_prismatic_recipe,
    write_solidworks_builder_script,
)
from recipe_selection import build_recipe
from residual_reconstruction import (
    _revolve_cut_candidate,
    recipe_solid,
    refine_recipe_with_residuals,
)


def _box_with_two_side_bosses() -> trimesh.Trimesh:
    base = trimesh.creation.box(extents=(10.0, 8.0, 2.0))
    bosses = []
    for x in (-6.0, 6.0):
        boss = trimesh.creation.box(extents=(2.0, 2.0, 0.5))
        boss.apply_translation([x, 0.0, 0.75])
        bosses.append(boss)
    return trimesh.boolean.union([base, *bosses])


def _box_with_blind_hole() -> trimesh.Trimesh:
    base = trimesh.creation.box(extents=(10.0, 8.0, 2.0))
    cutter = trimesh.creation.cylinder(radius=1.2, height=0.75, sections=64)
    cutter.apply_translation([0.0, 0.0, 0.625])
    return trimesh.boolean.difference([base, cutter])


def _mixed_extrude_revolve_cut_part() -> trimesh.Trimesh:
    base = trimesh.creation.box(extents=(30.0, 20.0, 8.0))
    base.apply_translation([0.0, 0.0, 4.0])
    boss = trimesh.creation.cylinder(radius=7.0, height=12.0, sections=96)
    boss.apply_translation([0.0, 0.0, 14.0])
    combined = trimesh.boolean.union([base, boss], engine="manifold")
    groove = trimesh.creation.torus(
        major_radius=7.0,
        minor_radius=1.4,
        major_sections=128,
        minor_sections=32,
    )
    groove.apply_translation([0.0, 0.0, 14.0])
    return trimesh.boolean.difference(
        [combined, groove], engine="manifold"
    )


def test_recipe_solid_executes_an_extrude_recipe() -> None:
    recipe = build_prismatic_recipe(
        trimesh.creation.box(extents=(10.0, 8.0, 2.0)),
        "mm",
        extrusion_index=0,
    )

    solid = recipe_solid(recipe)

    assert solid is not None
    assert solid.is_volume
    assert abs(solid.volume) == 160.0


def test_residual_loop_adds_localized_bosses() -> None:
    source = _box_with_two_side_bosses()
    base = build_prismatic_recipe(
        source, "mm", extrusion_index=0
    )

    refined = refine_recipe_with_residuals(
        source, base, "mm", minimum_improvement=0.001
    )

    added = [
        feature
        for feature in refined["features"]
        if feature["role"] == "residual_boss"
    ]
    assert refined["strategy"] == "residual_refined_reconstruction"
    assert len(added) == 2
    assert refined["confidence"] > base["confidence"]
    trace = refined["diagnostics"]["residual_refinement"]
    assert trace["attempted"] is True
    assert len(trace["accepted_features"]) == 2


def test_residual_loop_recovers_a_blind_cut() -> None:
    source = _box_with_blind_hole()
    base = build_prismatic_recipe(
        source, "mm", extrusion_index=0
    )

    refined = refine_recipe_with_residuals(
        source, base, "mm", minimum_improvement=0.001
    )

    cuts = [
        feature
        for feature in refined["features"]
        if feature["role"] == "residual_cut"
    ]
    assert len(cuts) == 1
    assert refined["confidence"] > base["confidence"]
    assert cuts[0]["start_offset"] >= 0.0
    assert cuts[0]["depth"] > 0.0
    assert cuts[0]["depth"] < base["features"][0]["depth"]
    assert cuts[0]["sketch"]["outer_loop"]["kind"] == "circle"
    assert cuts[0]["sketch"]["inferred_constraints"][0]["type"] == "diameter"


def test_solidworks_export_uses_a_native_circle_for_residual_hole(
    tmp_path,
) -> None:
    source = _box_with_blind_hole()
    base = build_prismatic_recipe(source, "mm", extrusion_index=0)
    refined = refine_recipe_with_residuals(
        source, base, "mm", minimum_improvement=0.001
    )
    script_path = tmp_path / "blind-hole.vbs"

    write_solidworks_builder_script(refined, script_path)

    script = script_path.read_text(encoding="ascii")
    assert script.count("CreateCircleByRadius") >= 1
    assert "CADView Residual Cut 1" in script


def test_exact_base_stops_without_adding_features() -> None:
    source = trimesh.creation.box(extents=(10.0, 8.0, 2.0))
    base = build_prismatic_recipe(source, "mm", extrusion_index=0)

    refined = refine_recipe_with_residuals(source, base, "mm")

    assert refined["strategy"] == "prismatic_extrusion"
    assert len(refined["features"]) == 1
    assert (
        refined["diagnostics"]["residual_refinement"]["stop_reason"]
        == "agreement_satisfied"
    )


def test_recipe_solid_executes_a_revolve_cut() -> None:
    body = trimesh.creation.cylinder(radius=10.0, height=12.0, sections=96)
    body.apply_translation([0.0, 0.0, 6.0])
    base = build_prismatic_recipe(body, "mm", extrusion_index=2)
    groove = trimesh.creation.torus(
        major_radius=8.0,
        minor_radius=1.0,
        major_sections=96,
        minor_sections=24,
    )
    groove.apply_translation([0.0, 0.0, 6.0])
    candidate = _revolve_cut_candidate(
        groove,
        base_strategy="prismatic_extrusion",
        axis_index=2,
        feature_id="test-revolve-cut",
        display_index=1,
    )
    assert candidate is not None
    _, feature = candidate
    base["features"].append(feature)

    solid = recipe_solid(base)

    assert solid is not None
    assert solid.is_volume
    assert solid.volume < recipe_solid(
        {**base, "features": base["features"][:1]}
    ).volume


def test_mixed_history_search_recovers_revolve_cut_and_cross_axis_base() -> None:
    recipe = build_recipe(_mixed_extrude_revolve_cut_part(), "mm")

    feature_types = [feature["type"] for feature in recipe["features"]]
    trace = recipe["diagnostics"]["residual_refinement"]
    assert recipe["confidence"] > 0.99
    assert "revolve_cut" in feature_types
    assert len(feature_types) >= 4
    assert trace["beam_width"] >= 3
    assert any(
        len(iteration["beam"]) > 1
        for iteration in trace["iterations"]
        if iteration["beam"]
    )


def test_solidworks_script_contains_native_revolve_cut(tmp_path) -> None:
    body = trimesh.creation.cylinder(radius=10.0, height=12.0, sections=96)
    body.apply_translation([0.0, 0.0, 6.0])
    recipe = build_prismatic_recipe(body, "mm", extrusion_index=2)
    groove = trimesh.creation.torus(
        major_radius=8.0,
        minor_radius=1.0,
        major_sections=96,
        minor_sections=24,
    )
    groove.apply_translation([0.0, 0.0, 6.0])
    candidate = _revolve_cut_candidate(
        groove,
        base_strategy="prismatic_extrusion",
        axis_index=2,
        feature_id="test-revolve-cut",
        display_index=1,
    )
    assert candidate is not None
    _, feature = candidate
    recipe["features"].append(feature)
    script_path = tmp_path / "revolve-cut.vbs"

    write_solidworks_builder_script(recipe, script_path)

    script = script_path.read_text(encoding="ascii")
    assert "True, True, False, True" in script
    assert "feature_ok=2:revolve_cut" in script
