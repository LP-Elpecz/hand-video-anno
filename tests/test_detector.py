import numpy as np
import pytest

from hand_anno import detector
from hand_anno.core import Cancelled, Project, Source
from hand_anno import gloved_model


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


def test_grounding_postprocess_clips_boxes_removes_duplicates_and_preserves_hand_label():
    import torch

    class FakeInputs(dict):
        input_ids = torch.zeros((1, 2), dtype=torch.long)

        def to(self, _):
            return self

    class FakeProcessor:
        def __call__(self, **kwargs):
            # OpenCV BGR input must be converted to RGB for Transformers.
            assert kwargs["images"][0, 0].tolist() == [3, 2, 1]
            assert kwargs["text"] == "gloved hand."
            return FakeInputs()

        def post_process_grounded_object_detection(self, outputs, ids, **kwargs):
            assert kwargs["target_sizes"] == [(10, 20)]
            assert kwargs["threshold"] == 0.4
            return [{"boxes": torch.tensor([[-5, 1, 15, 14], [0, 1, 15, 14], [40, 40, 50, 50], [18, 5, 30, 20.]]),
                     "scores": torch.tensor([0.9, 0.8, 0.7, 0.6])}]

    model = detector.GlovedHandDetector.__new__(detector.GlovedHandDetector)
    model.processor = FakeProcessor()
    model.model = lambda **_: None
    model.device = "cpu"
    model.prompt, model.confidence, model.text_threshold, model.nms_threshold = "gloved hand.", 0.4, 0.2, 0.5
    shapes = model.detect(np.full((10, 20, 3), [1, 2, 3], np.uint8))
    assert [s.box for s in shapes] == [[0, 1, 15, 10], [18, 5, 20, 10]]
    assert all(s.label == "hand" for s in shapes)
    assert shapes[0].score == pytest.approx(0.9)


def test_model_download_rejects_corrupt_cache_and_can_cancel_atomically(tmp_path, monkeypatch):
    import hashlib
    import io

    payload = b"a test model file"
    monkeypatch.setattr(gloved_model, "ASSETS", {"test.bin": hashlib.sha256(payload).hexdigest()})
    monkeypatch.setattr(gloved_model.urllib.request, "urlopen", lambda *_, **__: io.BytesIO(payload))
    cancelled = [False]

    def progress(*_):
        cancelled[0] = True

    with pytest.raises(Cancelled):
        gloved_model.download_gloved_model(tmp_path, progress, lambda: cancelled[0])
    assert not list(tmp_path.iterdir())
    gloved_model.download_gloved_model(tmp_path)
    assert (tmp_path / "test.bin").read_bytes() == payload
    (tmp_path / "test.bin").write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="校验失败"):
        gloved_model.download_gloved_model(tmp_path)
