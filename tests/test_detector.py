from um_detector.detector import count_fillers


def test_count_fillers_basic():
    text = "Um, I think you know, um, like, yes."
    result = count_fillers(text)
    assert result["um"] == 2
    assert result["i think"] == 1
    assert result["you know"] == 1
    assert result["like"] == 1
