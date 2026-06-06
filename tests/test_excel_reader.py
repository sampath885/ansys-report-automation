"""Excel reader tests."""

from ansys_report.excel.reader import read_design_calcs


def test_read_sample_calcs(sample_calcs_xlsx):
    result = read_design_calcs(sample_calcs_xlsx)
    assert len(result.bolt_load) >= 1
    fos_row = result.bolt_load[0]
    assert fos_row.label == "FOS"
    assert fos_row.value == 16.36
    assert fos_row.verdict == "ACCEPTABLE"
