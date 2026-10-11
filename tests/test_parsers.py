"""The pure parsers over recorded pages: Digitalarkivet, the National Library, Kartverket."""

from __future__ import annotations

import pytest

from norway_archives_mcp import digitalarkivet as da
from norway_archives_mcp import nb
from norway_archives_mcp import places as pl

from .conftest import FT, KB, KB_UUID, NB_PAGE51, SOURCE, fixture


# --------------------------------------------------------------------------- #
# Digitalarkivet
# --------------------------------------------------------------------------- #
def test_person_search_hits_carry_record_source_and_event():
    result = da.parse_persons(fixture("da_persons_roros.html"))
    assert result["total"] == 4 and result["pages"] == 1
    first = result["hits"][0]
    assert first["name"] == "Carl Ingvart Theodor Rønning"
    assert first["born"] == "1849"
    assert first["event_date"] == "1875-09-26"
    assert first["role"] == "far"
    assert first["record_url"].endswith("/en/view/255/pd00000024592808")
    assert first["source_id"] == SOURCE


def test_person_search_census_hit_keeps_domicile_and_position():
    census = da.parse_persons(fixture("da_persons_roros.html"))["hits"][2]
    assert "census/person" in census["record_url"]
    assert census["source"] == "1865 census for Røros"
    assert census["position"].startswith("Husfader")
    assert census["domicile"].startswith("Røraas")


def test_an_empty_result_page_is_zero_hits_not_an_error():
    assert da.parse_persons("<html><body><p>nothing</p></body></html>")["total"] == 0


def test_church_book_record_separates_person_event_people_and_source():
    record = da.parse_record(fixture("da_record_roros_baptism.html"), "u")
    assert record["permanent_id"] == "pd00000024592808"
    assert record["title"] == "Carl Ingvart Theodor Rønning"
    # The record's own fields describe this person (the father), not the source.
    assert record["fields"]["Role"] == "far"
    assert "Married" not in record["fields"]
    sections = {s["section"]: s for s in record["sections"]}
    assert len(sections["Persons involved"]["people"]) == 3
    assert sections["Births and baptisms"]["fields"]["Serial no."] == "85"
    assert record["about_the_source"]["Source information"]["Start year"] == "1860"
    assert record["source_id"] == SOURCE
    assert record["scanned_pages"] == [KB]


def test_census_record_lists_the_household_and_its_ft_scan():
    record = da.parse_record(fixture("da_census_person_roros_1865.html"), "u")
    assert record["fields"]["Place of birth"] == "Holtaalens Prgj."
    residents = next(s for s in record["sections"] if s["section"] == "Residents")
    assert len(residents["people"]) >= 5
    assert record["scanned_pages"] == [FT]


def test_a_page_without_a_permanent_id_is_reported_as_changed():
    with pytest.raises(da.PageChanged):
        da.parse_record("<html><body>maintenance</body></html>", "u")


def test_source_search_gives_each_list_with_scanned_and_searchable_flags():
    result = da.parse_sources(fixture("da_sources_roros_kf.html"))
    assert result["total"] == 2
    book = next(s for s in result["sources"] if s["source_id"] == SOURCE)
    confirmations = next(x for x in book["lists"] if x["list_type"] == "kf")
    assert confirmations == {
        "list_type": "kf",
        "label": "Confirmation",
        "years": "1860-1878",
        "scanned": True,
        "searchable": False,
    }


def test_source_page_gives_reference_and_section_starts():
    source = da.parse_source(fixture("da_source_6540.html"), SOURCE)
    assert source["title"] == "Church book from Røros parish 1860-1878 (1640P)"
    assert source["archive_reference"] == "AV/SAT-A-1456/681/L0932"
    codes = [s["list_type"] for s in source["sections"]]
    assert {"dp", "kf", "vi", "gr"} <= set(codes)
    assert source["first_page_uuid"]


def test_manifest_rows_carry_kb_service_and_restriction():
    manifest = da.parse_manifest(fixture("da_manifest_6540.json"))
    assert len(manifest["pages"]) == 464
    uuid, kb, width, height, restricted, service = manifest["pages"][150]
    assert (uuid, kb, restricted) == (KB_UUID, KB, False)
    assert service.endswith(KB_UUID) and width > 3000
    assert manifest["metadata"]["Archive reference"] == "AV/SAT-A-1456/681/L0932"


def test_a_manifest_of_the_wrong_kind_is_refused():
    with pytest.raises(da.PageChanged):
        da.parse_manifest({"@type": "sc:Manifest"})


@pytest.mark.parametrize(
    "ref",
    [
        "https://www.digitalarkivet.no/en/view/255/pd00000024592808",
        "https://www.digitalarkivet.no/view/255/pd00000024592808",
        "view/255/pd00000024592808",
    ],
)
def test_record_addresses_normalise_to_the_english_page(ref):
    assert da.record_url(ref) == "https://www.digitalarkivet.no/en/view/255/pd00000024592808"


def test_a_foreign_address_is_not_a_record():
    assert da.record_url("https://example.org/view/1/x") is None


def test_viewer_locations_parse():
    assert da.parse_viewer_location(
        f"https://nye.digitalarkivet.no/source/{SOURCE}/parish/{KB_UUID}"
    ) == (
        SOURCE,
        KB_UUID,
    )
    assert da.parse_old_viewer_location("https://media.digitalarkivet.no/view/38322/19") == (
        38322,
        19,
    )


def test_urn_and_iiif_image_addresses():
    assert da.urn_image_url(FT) == f"https://urn.digitalarkivet.no/URN:NBN:no-a1450-{FT}.jpg"
    assert da.image_url("https://x/svc", 2000).endswith("/full/!2000,2000/0/default.jpg")
    assert da.image_url("https://x/svc", None).endswith("/full/max/0/default.jpg")


def test_list_parameters_repeat_with_brackets():
    url = da.persons_url({"lastname": "Aas", "m": ["1640"], "lt": ["kf"], "page": None})
    assert "m%5B%5D=1640" in url and "lt%5B%5D=kf" in url and "page" not in url


# --------------------------------------------------------------------------- #
# National Library
# --------------------------------------------------------------------------- #
def test_library_search_shapes_access():
    result = nb.shape_search(fixture("nb_search.json"))
    assert result["total"] > 1000
    access = {i["readable_from"] for i in result["items"]}
    assert {"everywhere", "norway_only"} <= access


def test_a_single_item_record_names_its_author_from_people():
    item = nb.shape_item(fixture("nb_item_open.json"))
    assert item["creators"] and item["public_domain"] and item["readable_from"] == "everywhere"


def test_fragments_keep_the_printed_page_and_mark_the_match():
    hits = nb.shape_fragments(fixture("nb_fragments.json"))
    assert hits[0]["page"] == "51" and hits[0]["page_id"] == NB_PAGE51
    assert "**Hiort**" in hits[0]["snippet"]


def test_library_manifest_maps_printed_pages_to_page_ids():
    manifest = nb.parse_manifest(fixture("nb_manifest_open_first80.json"))
    page51 = next(row for row in manifest["pages"] if row[1] == "51")
    assert page51[0] == NB_PAGE51 and page51[4].endswith(NB_PAGE51)


def test_a_norway_only_manifest_still_lists_pages():
    manifest = nb.parse_manifest(fixture("nb_manifest_norway_only_first12.json"))
    assert manifest["pages"] and manifest["pages"][0][0].startswith("URN:NBN:")


def test_alto_text_reads_lines_in_order():
    text = nb.alto_text(fixture("nb_alto_page51.xml"))
    assert text.startswith("1670—1695. 51")
    assert len(text.splitlines()) > 30


def test_unreadable_alto_is_a_value_error():
    with pytest.raises(ValueError):
        nb.alto_text("<not-xml")


def test_ids_are_checked():
    assert nb.valid_item_id("6c40d98813a942688b706a97e15dde22")
    assert not nb.valid_item_id("../../etc")
    assert nb.valid_page_id(NB_PAGE51) and not nb.valid_page_id("x")


# --------------------------------------------------------------------------- #
# Places
# --------------------------------------------------------------------------- #
def test_municipalities_by_name_number_and_county():
    assert pl.municipalities("Røros")[0]["number"] == "1640"
    assert pl.municipalities("0301")[0]["name"] == "Oslo"
    assert all(m["county"] == "Hordaland" for m in pl.municipalities(county="Hordaland"))


def test_a_shared_name_is_ambiguous_until_the_county_is_given():
    number, candidates = pl.resolve_municipality("Kvam")
    assert number is None and len(candidates) >= 2
    number, candidates = pl.resolve_municipality("Kvam, Hordaland")
    assert number and candidates == []


def test_list_types_by_code_or_label():
    assert pl.list_type_code("kf") == "kf"
    assert pl.list_type_code("Out-migrated") == "uf"
    assert pl.list_type_code("nonsense") is None


def test_a_name_with_aa_is_not_folded_to_a():
    assert pl._fold("Åsnes") != pl._fold("Asnes")


def test_place_names_shape_and_map_link():
    result = pl.shape_place_names(fixture("kv_roros.json"))
    first = result["names"][0]
    assert first["name"] == "Røros" and first["latitude"] and "norgeskart" in first["map"]


def test_kartverket_filters_by_number_or_name():
    assert "knr=5025" in pl.kartverket_url(
        "X", municipality="5025", county="", fuzzy=False, limit=5
    )
    assert "kommunenavn=R" in pl.kartverket_url(
        "X", municipality="Røros", county="", fuzzy=True, limit=5
    )
