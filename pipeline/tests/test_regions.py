from pipeline.common import load_regions, published_regions
from pipeline.tests.conftest import ROOT

ISO_CURRENT = set("""AD AL ALT AMU ARK AST BA BEL BRY BU CE CHE CHU CU DA IN IRK IVA KAM KB KC KDA KEM KGD KGN KHA KHM KIR
KK KL KLU KO KOS KR KRS KYA LEN LIP MAG ME MO MOS MOW MUR NEN NGR NIZ NVS OMS ORE ORL PER PNZ PRI PSK ROS RYA SA SAK
SAM SAR SE SMO SPE STA SVE TA TAM TOM TUL TVE TY TYU UD ULY VGG VLA VLG VOR YAN YAR YEV ZAB""".split())


def test_iso_codes_match_current_list():
    regions = published_regions(load_regions(ROOT))
    assert {r["id"][3:] for r in regions} == ISO_CURRENT
    assert len(regions) == 83


def test_names_and_links():
    regions = published_regions(load_regions(ROOT))
    assert all(r["name"] and r["name_genitive"] and r["verified"] == "true" for r in regions)
    assert {r["id"]: r["route"] for r in regions if r["route"]} == {
        "RU-KGD": "ru-kgd", "RU-KOS": "ru-kos", "RU-SVE": "ru-sve", "RU-PSK": "ru-psk-children"}
    assert {r["id"]: r["router"] for r in regions if r["router"]} == {
        "RU-MOW": "ru-mow", "RU-MOS": "ru-mos", "RU-SPE": "spb-lo", "RU-LEN": "spb-lo"}
    aliases = [a.lower() for r in regions for a in r["aliases"].split(";") if a]
    assert len(aliases) == len(set(aliases))
