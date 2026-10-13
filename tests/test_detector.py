import numpy as np
import pytest

from hand_anno import detector
from hand_anno.core import Cancelled, Project, Source


def test_cancel_during_final_inference_discards_results(monkeypatch):
    class FakeDetector:
        def __init__(self, *_):
            pass

        def detect(self, image):
            return []

    class FakeReader:
        def __init__(self, *_):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def read(self, index):
            return np.zeros((10, 10, 3), np.uint8)

    monkeypatch.setattr(detector, "HandDetector", FakeDetector)
    monkeypatch.setattr(detector, "FrameReader", FakeReader)
    cancelled = [False]

    def progress(done, total, message):
        if done == 1:
            cancelled[0] = True

    project = Project(Source("unused", "video", 5, 1, 10, 10))
    with pytest.raises(Cancelled):
        detector.detect_project(project, [0], progress=progress, cancelled=lambda: cancelled[0])
    assert not project.frames
