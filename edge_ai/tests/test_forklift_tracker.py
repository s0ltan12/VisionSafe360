import sys
from pathlib import Path

_EDGE_AI_DIR = Path(__file__).resolve().parents[1]
if str(_EDGE_AI_DIR) not in sys.path:
    sys.path.insert(0, str(_EDGE_AI_DIR))

from src.analysis.forklift_tracker import ForkliftTracker, ForkliftTrackerConfig
from src.analysis.proximity_analyzer import ProximityAnalyzer
from src.models.detection import Detection


def _forklift(bbox, conf=0.9, track_id=None):
    return Detection(
        class_id=5,
        class_name="forklift",
        confidence=conf,
        bbox=bbox,
        track_id=track_id,
    )


def _person(bbox, track_id=1):
    return Detection(
        class_id=0,
        class_name="person",
        confidence=0.9,
        bbox=bbox,
        track_id=track_id,
    )


def test_track_id_persists_across_updates():
    tracker = ForkliftTracker()
    first = _forklift((100, 100, 240, 220))
    second = _forklift((112, 103, 252, 223))

    tracker.update([first], 100.0)
    tracker.update([second], 100.1)

    assert first.track_id is not None
    assert second.track_id == first.track_id


def test_lost_track_recovers_after_temporary_occlusion():
    tracker = ForkliftTracker(ForkliftTrackerConfig(max_lost_frames=3))
    first = _forklift((100, 100, 240, 220))
    recovered = _forklift((118, 106, 258, 226))

    tracker.update([first], 100.0)
    tracker.update([], 100.1)
    tracker.update([], 100.2)
    tracker.update([recovered], 100.3)

    assert recovered.track_id == first.track_id
    assert tracker.get(first.track_id).lost_frames == 0


def test_reappearing_after_purge_gets_new_track_id():
    tracker = ForkliftTracker(ForkliftTrackerConfig(max_lost_frames=1))
    first = _forklift((100, 100, 240, 220))
    reappeared = _forklift((118, 106, 258, 226))

    tracker.update([first], 100.0)
    tracker.update([], 100.1)
    tracker.update([], 100.2)
    tracker.update([reappeared], 100.3)

    assert reappeared.track_id != first.track_id


def test_multiple_forklifts_keep_unique_ids():
    tracker = ForkliftTracker()
    a1 = _forklift((100, 100, 220, 220))
    b1 = _forklift((400, 100, 520, 220))
    a2 = _forklift((125, 100, 245, 220))
    b2 = _forklift((375, 100, 495, 220))

    tracker.update([a1, b1], 100.0)
    tracker.update([a2, b2], 100.1)

    assert len({a2.track_id, b2.track_id}) == 2
    assert a2.track_id == a1.track_id
    assert b2.track_id == b1.track_id


def test_proximity_event_includes_forklift_track_id():
    analyzer = ProximityAnalyzer(danger_px=260.0, warning_px=320.0)
    forklift = _forklift((100, 100, 240, 220))
    worker = _person((260, 130, 320, 250), track_id=7)

    events = analyzer.analyze(
        [worker, forklift],
        tracked_pose_people=[worker],
        camera_id="cam_01",
        frame_number=1,
        timestamp=100.0,
    )

    assert len(events) == 1
    assert events[0].metadata["forklift_track_id"] == forklift.track_id


def test_prepare_detections_deduplicates_overlapping_forklifts_before_render_or_analysis():
    analyzer = ProximityAnalyzer()
    worker = _person((260, 130, 320, 250), track_id=7)
    low_conf = _forklift((100, 100, 240, 220), conf=0.6)
    high_conf = _forklift((105, 102, 245, 222), conf=0.95)

    prepared = analyzer.prepare_detections(
        [worker, low_conf, high_conf],
        timestamp=100.0,
    )
    forklifts = [d for d in prepared if d.class_name == "forklift"]

    assert len(forklifts) == 1
    assert forklifts[0] is high_conf
    assert forklifts[0].track_id is not None

    events = analyzer.analyze(
        prepared,
        tracked_pose_people=[worker],
        camera_id="cam_01",
        frame_number=1,
        timestamp=100.0,
        detections_are_prepared=True,
    )

    assert len(events) == 1
    assert events[0].metadata["forklift_track_id"] == forklifts[0].track_id


def test_prepare_detections_keeps_distinct_forklifts_as_unique_tracks():
    analyzer = ProximityAnalyzer()
    worker = _person((260, 130, 320, 250), track_id=7)
    left = _forklift((100, 100, 220, 220))
    right = _forklift((500, 100, 620, 220))

    prepared = analyzer.prepare_detections(
        [worker, left, right],
        timestamp=100.0,
    )
    forklifts = [d for d in prepared if d.class_name == "forklift"]

    assert len(forklifts) == 2
    assert len({d.track_id for d in forklifts}) == 2
