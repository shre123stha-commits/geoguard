def test_scene_caps_keep_clearest_and_spread():
    from datetime import UTC, datetime

    from app.pipeline.composite import select_optical, select_radar
    from app.pipeline.sources.base import SceneRef

    def s2(i, cc):
        return SceneRef(f"s2-{i}", "sentinel2", datetime(2024, 1, 1 + i, tzinfo=UTC), cc)

    scenes = [s2(i, cc) for i, cc in enumerate([50, 5, 40, 1, 30, 20, 60, 10])]
    kept = select_optical(scenes, cap=3)
    assert [s.scene_id for s in kept] == ["s2-1", "s2-3", "s2-7"]  # clearest, in date order
    assert select_optical(scenes[:2], cap=3) == scenes[:2]

    s1 = [SceneRef(f"s1-{i}", "sentinel1", datetime(2024, 1, 1 + i, tzinfo=UTC)) for i in range(20)]
    kept = select_radar(s1, cap=5)
    assert [s.scene_id for s in kept] == ["s1-0", "s1-5", "s1-10", "s1-14", "s1-19"]
    assert select_radar(s1[:4], cap=5) == s1[:4]
