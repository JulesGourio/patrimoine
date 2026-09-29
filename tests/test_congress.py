from patrimoine.sources.congress import parse_house_pdf, parse_senate_html, politician_id

N = "\x00"
HOUSE_TEXT = f"""Name: Hon. Nancy Pelosi
Status: Member
ID Owner Asset Transaction
Type
Date Notification
Date
Amount Cap.
Gains >
$200?
SP Bloom Energy Corporation Class A
Common Stock (BE) [ST]
P 07/24/2026 07/24/2026 $1,000,001 -
$5,000,000
F{N * 5} S{N * 5}: New
D{N * 10}: Purchased 10,000 shares.
SP Alphabet Inc. - Class A Common Stock
(GOOGL) [OP]
P 07/24/2026 07/24/2026 $250,001 -
$500,000
F{N * 5} S{N * 5}: New
D{N * 10}: Exercised 50 call options purchased 1/14/25 (5,000 shares) at a strike price of $100 on
1/16/26. SP Intel Corporation - Common Stock (INTC) [ST]
S (partial) 07/28/2026 07/28/2026 Over $50,000,000
F{N * 5} S{N * 5}: New
Filing ID #20035143
"""

SENATE_HTML = """<table><thead><tr><th>#</th></tr></thead><tbody>
<tr><td>1</td><td>09/01/2026</td><td>Spouse</td><td><a href="x">WFC</a></td><td>Wells Fargo &amp; Company</td>
<td>Stock</td><td>Purchase</td><td>$15,001 - $50,000</td><td>--</td></tr>
<tr><td>2</td><td>08/04/2026</td><td>Joint</td><td>--</td><td>Electronic Arts Inc. (EA)</td>
<td>Stock</td><td>Sale (Partial)</td><td>$1,001 - $15,000</td><td>Corporate action</td></tr>
</tbody></table>"""


def test_house_pdf_trades():
    t = parse_house_pdf(HOUSE_TEXT)
    assert [(x["ticker"], x["action"], x["asset_type"], x["owner"]) for x in t] == [
        ("BE", "achat", "action", "Conjoint"), ("GOOGL", "achat", "option", "Conjoint"),
        ("INTC", "vente partielle", "action", "Conjoint")]
    assert t[0]["tx_date"] == "2026-07-24" and (t[0]["amount_min"], t[0]["amount_max"]) == (1000001, 5000000)
    assert t[0]["comment"] == "Purchased 10,000 shares."
    assert t[1]["comment"].endswith("1/16/26.")  # wrapped description stays with its trade
    assert t[2]["asset"] == "Intel Corporation - Common Stock (INTC)"
    assert (t[2]["amount_min"], t[2]["amount_max"]) == (50000000, None)


def test_senate_html_trades():
    t = parse_senate_html(SENATE_HTML)
    assert [(x["ticker"], x["action"], x["owner"]) for x in t] == [("WFC", "achat", "Conjoint"),
                                                                     ("EA", "vente partielle", "Commun")]
    assert t[0]["asset"] == "Wells Fargo & Company" and t[0]["comment"] is None


def test_politician_ids_match_across_name_forms():
    assert politician_id("senate", "McConnell, Jr.", "A. Mitchell") == "senate:MCCONNELL MITCHELL"
    assert politician_id("senate", "Tuberville", "Thomas H") == "senate:TUBERVILLE THOMAS"
    assert politician_id("senate", "Moran,", "Jerry") == "senate:MORAN JERRY"
    assert politician_id("house", "Pelosi", "Nancy") == "house:PELOSI NANCY"


def test_house_trade_cut_by_a_page_break():
    header = "ID Owner Asset Transaction\nType\nDate Notification\nDate\nAmount Cap.\nGains >\n$200?\n"
    text = (header + "CoStar Group, Inc. - Common Stock\n(CSGP) [ST]\nP 08/19/2026 09/04/2026 $1,001 - $15,000\n"
            "F S: New\nCrowdStrike Holdings, Inc. - Class A P 08/07/2026 09/04/2026 $1,001 - $15,000\n" + header +
            "Common Stock (CRWD) [ST]\nF S: New\nCrown Castle Inc. Common Stock\n(CCI) [ST]\n"
            "S (partial) 08/18/2026 09/04/2026 $1,001 - $15,000\nF S: New\n")
    t = parse_house_pdf(text)
    assert [(x["ticker"], x["action"], x["tx_date"]) for x in t] == [
        ("CSGP", "achat", "2026-08-19"), ("CRWD", "achat", "2026-08-07"), ("CCI", "vente partielle", "2026-08-18")]
    assert t[2]["asset"] == "Crown Castle Inc. Common Stock (CCI)"
