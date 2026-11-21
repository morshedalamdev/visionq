import math

import pytest

from worker import evaluation as ev

A = [0.0, 0.0, 10.0, 10.0]
B = [20.0, 0.0, 30.0, 10.0]
ELSEWHERE = [20.0, 20.0, 30.0, 30.0]


def p(cls, conf, box):
    return {"cls": cls, "conf": conf, "box": box}


def g(cls, box):
    return {"cls": cls, "box": box}


def test_duplicate_detection_matches_one_truth_once():
    # Same box twice: first is TP, duplicate is FP. Wrong class is FP for class 1.
    result = ev.match_image([p(0, 0.9, A), p(0, 0.8, A), p(1, 0.7, A)], [g(0, A)], 0.0)
    assert result["tp"][0] == 1
    assert result["fp"][0] == 1 and result["fp"][1] == 1
    assert sum(result["fn"]) == 0


def test_iou_boundary_is_inclusive_and_below_is_miss():
    # [0,0,10,5] vs A: inter 50, union 100 + 50 - 50 = 100 -> IoU 0.5 exactly.
    assert ev.iou([0, 0, 10, 5], A) == pytest.approx(0.5)
    assert ev.match_image([p(0, 0.9, [0, 0, 10, 5])], [g(0, A)], 0.0)["tp"][0] == 1
    # [0,0,10,4]: IoU 0.4 -> FP and FN.
    miss = ev.match_image([p(0, 0.9, [0, 0, 10, 4])], [g(0, A)], 0.0)
    assert (miss["tp"][0], miss["fp"][0], miss["fn"][0]) == (0, 1, 1)


def test_one_to_one_greedy_prefers_best_overlap():
    # g1=[0,0,10,10], g2=[5,0,15,10]. High-confidence [4,0,14,10] has IoU 60/140
    # with g1 and 90/110 with g2, so it takes g2; the second box then takes g1.
    g1, g2 = A, [5.0, 0.0, 15.0, 10.0]
    result = ev.match_image(
        [p(0, 0.9, [4, 0, 14, 10]), p(0, 0.5, g1)],
        [g(0, g1), g(0, g2)],
        0.0,
    )
    assert sorted((m[0], m[1]) for m in result["matches"]) == [(0, 1), (1, 0)]
    assert result["fp"][0] == 0 and result["fn"][0] == 0


def test_threshold_drops_low_confidence_predictions():
    result = ev.match_image([p(0, 0.3, A)], [g(0, A)], 0.5)
    assert (result["tp"][0], result["fn"][0]) == (0, 1)


IMAGES = [
    ([p(0, 0.9, A), p(1, 0.4, B)], [g(0, A), g(1, B)]),
    ([p(0, 0.8, A), p(0, 0.6, ELSEWHERE)], [g(0, A)]),
]


def test_prf_and_macro_f1_hand_values():
    # t=0.5: class0 tp2 fp1 fn0 -> P 2/3, R 1, F1 4/5. class1 .4 dropped ->
    # tp0 fp0 fn1: precision undefined, recall 0, F1 0. Macro = (0.8 + 0) / 2.
    result = ev.evaluate_at(IMAGES, 0.5)
    c0, c1 = result["per_class"][0], result["per_class"][1]
    assert c0["precision"] == pytest.approx(2 / 3) and c0["f1"] == pytest.approx(0.8)
    assert c1["precision"] is None and c1["recall"] == 0 and c1["f1"] == 0
    assert result["macro_f1"] == pytest.approx(0.4)
    assert result["unsupported_classes"] == [2, 3, 4, 5]


def test_unsupported_class_excluded_from_macro_but_fp_counted():
    # class 2 has no truth: its FP counts in micro (tp1 fp1 -> F1 2/3) but not macro.
    result = ev.evaluate_at([([p(0, 0.9, A), p(2, 0.9, A)], [g(0, A)])], 0.5)
    assert result["per_class"][2]["fp"] == 1
    assert result["micro"]["fp"] == 1
    assert result["per_class"][2]["f1"] is None
    assert result["macro_f1"] == pytest.approx(1.0)
    assert result["micro"]["f1"] == pytest.approx(2 / 3)


def test_threshold_selection_custom_grid():
    # Macro-F1: t=0.3 -> (0.8 + 1)/2 = 0.9; t=0.5 -> 0.4; t=0.7 -> (1 + 0)/2 = 0.5.
    chosen = ev.select_threshold(IMAGES, thresholds=(0.3, 0.5, 0.7))["selected"]
    assert chosen["threshold"] == 0.3
    assert chosen["macro_f1"] == pytest.approx(0.9)


def test_tie_break_prefers_higher_threshold_and_is_deterministic():
    # Macro-F1 is 0.9 for every t <= 0.4 (class-1 prediction at 0.4 kept), with
    # equal FP+FN, so the higher threshold 0.4 wins.
    first = ev.select_threshold(IMAGES)
    assert first["selected"]["threshold"] == 0.4
    assert len(first["search"]) == 99
    assert first == ev.select_threshold(IMAGES)


def test_zero_support_and_bad_grids_rejected():
    with pytest.raises(ValueError, match="no supported classes"):
        ev.select_threshold([([p(0, 0.9, A)], [])])
    for grid in ((), (0.5, 0.5), (0.0, 0.5), (0.5, 1.2)):
        with pytest.raises(ValueError):
            ev.select_threshold(IMAGES, thresholds=grid)


@pytest.mark.parametrize(
    "pred",
    [
        p(0, math.nan, A),
        p(0, 1.5, A),
        p(9, 0.5, A),
        p(0, 0.5, [5, 5, 5, 9]),
        p(0, 0.5, [0, 0, math.inf, 5]),
    ],
)
def test_malformed_predictions_rejected(pred):
    with pytest.raises(ValueError):
        ev.match_image([pred], [], 0.5)
    with pytest.raises(ValueError, match="threshold"):
        ev.match_image([], [], 1.5)


def test_checkpoint_selection_rule():
    tie = {"best": {"map50_95": 0.5}, "last": {"map50_95": 0.5}}
    assert ev.select_checkpoint(tie) == "best"
    assert ev.select_checkpoint({**tie, "last": {"map50_95": 0.6}}) == "last"
    assert ev.select_checkpoint({"last": {"map50_95": 0.1}}) == "last"
    with pytest.raises(ValueError):
        ev.select_checkpoint({"best": {"map50_95": math.nan}})
    with pytest.raises(ValueError, match="no candidate"):
        ev.select_checkpoint({})
