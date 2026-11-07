from audit.cms_data import load_cms_data, parse_mue, parse_ncci, parse_pfs, sample_cms_data

NCCI = (
    "Column 1\tColumn 2\t*=in existence prior to 1996\tEffective Date\tDeletion Date\tModifier\tRationale\n"
    "99213\t36415\t\t20100101\t*\t1\tStandard preparation\n"
    "99213\t99211\t*\t19960101\t20201231\t0\tMutually exclusive\n"
    "00000\t11111\t\t20200101\t*\t9\tNot applicable\n"
    "this is a preamble line\n"
)
MUE = ('Practitioner MUE\n"HCPCS/CPT Code","Practitioner Services MUE Values","MUE Adjudication Indicator","Rationale"\n'
       '"99213","1","3 Date of Service Edit: Clinical","Clinical"\n"J1234","4","1 Line Edit","Code"\n')
PFS = ('Header text\nHCPCS,MOD,DESCRIPTION,STATUS CODE,WORK RVU,NON-FAC TOTAL,FACILITY TOTAL,CONV FACTOR\n'
       '99213,,Office visit,A,1.3,2.70,1.9,33.00\n99213,26,Office visit,A,1.3,1.0,1.0,33.00\n')


def test_parse_ncci_indicators_and_dates():
    t = parse_ncci(NCCI)
    assert len(t) == 3
    e = t.lookup("99213", "36415", "2024-06-01")
    assert e and e.indicator == "1" and e.deletion is None
    assert t.lookup("99213", "99211", "2020-12-31").indicator == "0"  # last day in effect
    assert t.lookup("99213", "99211", "2021-01-01") is None  # after deletion
    assert t.lookup("99213", "36415", "2009-12-31") is None  # before effective
    assert t.lookup("00000", "11111", "2024-01-01").indicator == "9"


def test_parse_mue_and_pfs():
    m = parse_mue(MUE)
    assert m["99213"].limit == 1 and m["99213"].mai == "3" and m["J1234"].mai == "1"
    assert parse_pfs(PFS) == {"99213": 89.1}  # modifier row ignored


def test_load_from_dir_and_manifest_fallback(tmp_path):
    (tmp_path / "ncci_practitioner").mkdir()
    (tmp_path / "ncci_practitioner" / "a.txt").write_text(NCCI)
    (tmp_path / "mue_practitioner").mkdir()
    (tmp_path / "mue_practitioner" / "m.csv").write_text(MUE)
    d = load_cms_data(tmp_path)
    assert d.source == "cms" and len(d.ncci) == 3 and "99213" in d.mue
    assert load_cms_data(tmp_path / "empty").source == "sample"
    assert sample_cms_data().source == "sample"


def test_partial_data_falls_back_per_dataset(tmp_path):
    (tmp_path / "mue_practitioner").mkdir()
    (tmp_path / "mue_practitioner" / "m.csv").write_text(MUE)
    d = load_cms_data(tmp_path)
    assert d.parts == {"ncci": "sample", "mue": "cms", "pfs": "none"}
    assert d.ncci.lookup("80053", "82947", "2024-03-05") is not None  # sample pair still available
