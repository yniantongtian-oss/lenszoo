import copy
from argparse import Namespace

import pytest

from lenszoo.schema import Prescription, SchemaError


def document():
    return {'id': 'boundary', 'surfaces': [
        {'name': 'OBJ', 'role': 'object', 'radius': 'inf', 'thickness': 'inf'},
        {'name': 'S1', 'radius': 10.0, 'thickness': 1.0, 'nd': 1.5, 'aspheric': {'A4': 0.001}},
        {'name': 'IMA', 'role': 'image'},
    ]}


@pytest.mark.parametrize('factor', [0, -1, float('nan'), float('inf')])
def test_scale_must_be_positive_and_finite(factor):
    with pytest.raises(ValueError, match='positive finite'):
        Prescription.from_dict(document()).scaled(factor)


@pytest.mark.parametrize('field', ['conic', 'radius', 'thickness'])
def test_nan_surface_parameters_are_rejected(field):
    data = document()
    data['surfaces'][1][field] = float('nan')
    with pytest.raises(SchemaError):
        Prescription.from_dict(data)


@pytest.mark.parametrize('value', [0, -0.5, float('nan'), float('inf')])
def test_invalid_wavelengths_are_rejected(value):
    data = document()
    data['wavelengths_um'] = [value]
    with pytest.raises(SchemaError):
        Prescription.from_dict(data)


def test_nonfinite_aspheric_coefficient_is_rejected():
    data = document()
    data['surfaces'][1]['aspheric']['A4'] = float('inf')
    with pytest.raises(SchemaError):
        Prescription.from_dict(data)


def test_infinity_convention_and_geometric_scaling_are_preserved():
    original = Prescription.from_dict(document())
    scaled = original.scaled(2)
    assert scaled.surfaces[0].thickness == float('inf')
    assert scaled.surfaces[1].radius == 20
    assert scaled.surfaces[1].aspheric['A4'] == pytest.approx(0.001 / 8)


@pytest.mark.parametrize('status,exit_code', [('failed', 1), ('needs_review', 1), ('plausible', 0), ('verified', 0), ('verified_refined', 0)])
def test_verify_command_exposes_failed_verification(tmp_path, monkeypatch, status, exit_code):
    from lenszoo import cli, verify
    file = tmp_path / 'input.json'
    Prescription.from_dict(document()).save(file)
    result = {'status': status, 'checks': {'efl': {'pass': exit_code == 0}}, 'failed_checks': ['efl'] if exit_code else []}
    monkeypatch.setattr(verify, 'verify', lambda _p: copy.deepcopy(result))
    assert cli.cmd_verify(Namespace(files=[file], write=False)) == exit_code
