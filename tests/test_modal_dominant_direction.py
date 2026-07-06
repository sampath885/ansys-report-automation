"""Tests for modal dominant-direction labelling."""

from ansys_report.extract.modal_direction import dominant_direction_from_ratios

# EP1581 reference Table 12 effective-mass ratios (modes 1–6).
_EP1581_RATIOS = [
    {
        "x": 0.325557e-05,
        "y": 0.370223e-05,
        "z": 0.767487,
        "rot_x": 0.146251,
        "rot_y": 0.249109,
        "rot_z": 0.107570e-05,
    },
    {
        "x": 0.272464,
        "y": 0.939157e-02,
        "z": 0.773764e-05,
        "rot_x": 0.500242e-02,
        "rot_y": 0.142975,
        "rot_z": 0.345692,
    },
    {
        "x": 0.263757e-04,
        "y": 0.391281e-04,
        "z": 0.931298e-01,
        "rot_x": 0.187182,
        "rot_y": 0.327936e-01,
        "rot_z": 0.716412e-04,
    },
    {
        "x": 0.646335e-12,
        "y": 0.594445e-06,
        "z": 0.728887e-02,
        "rot_x": 0.277976e-02,
        "rot_y": 0.128337e-02,
        "rot_z": 0.691161e-05,
    },
    {
        "x": 0.162929e-02,
        "y": 0.184519e-01,
        "z": 0.418334e-05,
        "rot_x": 0.920896e-02,
        "rot_y": 0.970181e-03,
        "rot_z": 0.695307e-02,
    },
    {
        "x": 0.388191e-02,
        "y": 0.841938e-03,
        "z": 0.239594e-01,
        "rot_x": 0.644488e-02,
        "rot_y": 0.267657e-01,
        "rot_z": 0.685120e-05,
    },
]

_EP1581_DIRECTIONS = [
    "Rotation about X & Rotation about Y & Z Direction",
    "Rotation about Y & Rotation about Z & X Direction",
    "Rotation about X",
    "Z Direction",
    "Y Direction",
    "Rotation about Y",
]


def test_dominant_direction_matches_ep1581_reference():
    for ratios, expected in zip(_EP1581_RATIOS, _EP1581_DIRECTIONS, strict=True):
        assert dominant_direction_from_ratios(ratios) == expected


def test_dominant_direction_none_when_empty():
    assert dominant_direction_from_ratios(None) is None
    assert dominant_direction_from_ratios({}) is None
