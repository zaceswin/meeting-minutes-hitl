from minutes import metrics


def test_wer_basic():
    r = metrics.wer("the levy is 500 shillings", "the levy is 600 shillings now")
    assert r["substitutions"] == 1 and r["insertions"] == 1 and r["deletions"] == 0
    assert abs(r["wer"] - 2 / 5) < 1e-9


def test_number_recall():
    r = metrics.number_recall("pay 500 and 4500 and 300", "pay 500 and 4000 and 300")
    assert r["numbers_correct"] == 2 and r["numbers_in_reference"] == 3


def test_item_scores(demo):
    sc = metrics.item_scores(demo, {"decision": [["L005"], ["L009"]], "action": [["L006"]], "open_issue": [["L007"]]})
    assert sc["decision"]["precision"] == 1.0 and sc["decision"]["recall"] == 0.5
    assert sc["action"]["recall"] == 1.0


def test_ffmpeg_cmd_filters():
    from minutes.preprocess import build_ffmpeg_cmd
    cmd = build_ffmpeg_cmd("a.m4a", "b.wav")
    assert "afftdn" not in " ".join(cmd) and "highpass=f=100" in " ".join(cmd)
    assert "afftdn" in " ".join(build_ffmpeg_cmd("a.m4a", "b.wav", denoise=True))
