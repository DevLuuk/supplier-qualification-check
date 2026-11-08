from supplier_check.lookups import (
    NAME_PASS_SCORE,
    SANCTIONS_UNSURE_SCORE,
    lookup_register,
    name_score,
    name_status,
    normalise,
    sanctions_status,
    screen_sanctions,
)


def test_umlauts_are_folded():
    assert normalise("Müller Gerüstbau Größe Öl") == "mueller geruestbau groesse oel"


def test_legal_forms_are_stripped():
    assert normalise("Müller Gerüstbau GmbH & Co. KG") == "mueller geruestbau"
    assert normalise("Weber Stahlbau GmbH") == "weber stahlbau"
    assert normalise("WestCert Prüf- und Zertifizierungsgesellschaft mbH") == (
        "westcert pruef und zertifizierungsgesellschaft"
    )
    assert normalise("Nordlicht Versicherung AG") == "nordlicht versicherung"


def test_legal_form_inside_word_is_kept():
    assert normalise("Agrar Bau GmbH") == "agrar bau"


def test_near_miss_scores_below_pass():
    score = name_score("Weber Stahlbau GmbH", "Weber Stahlbau Handels GmbH")
    assert score < NAME_PASS_SCORE
    assert name_status("Weber Stahlbau GmbH", "Weber Stahlbau Handels GmbH")[0] == "unsure"


def test_same_name_passes():
    assert name_status("Weber Stahlbau GmbH", "Weber  Stahlbau GmbH") == ("pass", 1.0)


def test_transliterated_name_is_unsure_not_pass():
    status, score = name_status("Müller Gerüstbau GmbH", "Mueller Geruestbau GmbH")
    assert (status, score) == ("unsure", 1.0)


def test_other_firm_fails():
    assert name_status("Weber Stahlbau GmbH", "Koch Tiefbau GmbH")[0] == "fail"


def test_empty_names_do_not_crash():
    assert name_status("", "Weber Stahlbau GmbH")[0] == "fail"


def test_register_lookup_is_mock():
    found = lookup_register("HRB 774102")
    assert found.match == "Weber Stahlbau GmbH"
    assert found.note.startswith("MOCK: ")
    missing = lookup_register("HRB 000000")
    assert missing.match is None
    assert missing.note.startswith("MOCK: ")


def test_sanctions_near_miss_passes():
    result = screen_sanctions("Hansen Elektrotechnik GmbH")
    assert result.match == "Hansen Elektro Trading Ltd"
    assert result.score < SANCTIONS_UNSURE_SCORE
    assert sanctions_status(result) == "pass"
    assert result.note.startswith("MOCK: ")


def test_sanctions_exact_fails_and_close_is_unsure():
    assert sanctions_status(screen_sanctions("Orlov Metallhandel OOO")) == "fail"
    assert sanctions_status(screen_sanctions("Kesselring Beteiligung AG")) == "unsure"
