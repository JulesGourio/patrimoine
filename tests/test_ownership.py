from patrimoine.fresh import _norm, _role
from patrimoine.sources.congress import fix_date
from patrimoine.sources.ownership import parse_ark_csv, parse_form4, parse_insider_table, parse_schedule13

FORM4 = b"""<?xml version="1.0"?>
<ownershipDocument>
  <issuer><issuerCik>0000920760</issuerCik><issuerName>LENNAR CORP /NEW/</issuerName>
    <issuerTradingSymbol>LEN, LEN.B</issuerTradingSymbol></issuer>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <securityTitle><value>Class A Common Stock</value></securityTitle>
      <transactionDate><value>2026-09-23</value></transactionDate>
      <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
      <transactionAmounts><transactionShares><value>532993</value></transactionShares>
        <transactionPricePerShare><value>81.65</value></transactionPricePerShare></transactionAmounts>
      <postTransactionAmounts><sharesOwnedFollowingTransaction><value>24252102</value></sharesOwnedFollowingTransaction>
      </postTransactionAmounts>
      <ownershipNature><directOrIndirectOwnership><value>I</value></directOrIndirectOwnership></ownershipNature>
    </nonDerivativeTransaction>
    <nonDerivativeTransaction>
      <securityTitle><value>Class A Common Stock</value></securityTitle>
      <transactionDate><value>2026-09-24</value></transactionDate>
      <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
      <transactionAmounts><transactionShares><value>399238</value></transactionShares>
        <transactionPricePerShare><value>80.58</value></transactionPricePerShare></transactionAmounts>
      <postTransactionAmounts><sharesOwnedFollowingTransaction><value>24651340</value></sharesOwnedFollowingTransaction>
      </postTransactionAmounts>
      <ownershipNature><directOrIndirectOwnership><value>I</value></directOrIndirectOwnership></ownershipNature>
    </nonDerivativeTransaction>
    <nonDerivativeTransaction>
      <securityTitle><value>Class B Common Stock</value></securityTitle>
      <transactionDate><value>2026-09-24</value></transactionDate>
      <transactionCoding><transactionCode>A</transactionCode></transactionCoding>
      <transactionAmounts><transactionShares><value>7022</value></transactionShares></transactionAmounts>
      <postTransactionAmounts><sharesOwnedFollowingTransaction><value>548892</value></sharesOwnedFollowingTransaction>
      </postTransactionAmounts>
      <ownershipNature><directOrIndirectOwnership><value>I</value></directOrIndirectOwnership></ownershipNature>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>"""

SCHEDULE_13G = b"""<?xml version="1.0" encoding="UTF-8"?>
<edgarSubmission xmlns="http://www.sec.gov/edgar/schedule13g">
  <formData>
    <coverPageHeader>
      <eventDateRequiresFilingThisStatement>03/31/2026</eventDateRequiresFilingThisStatement>
      <issuerInfo><issuerCik>0002039972</issuerCik><issuerName>Guardian Metal Resources PLC</issuerName>
        <issuerCusips><issuerCusipNumber>401382106</issuerCusipNumber></issuerCusips></issuerInfo>
    </coverPageHeader>
    <coverPageHeaderReportingPersonDetails>
      <reportingPersonBeneficiallyOwnedAggregateNumberOfShares>24699825</reportingPersonBeneficiallyOwnedAggregateNumberOfShares>
      <classPercent>12.7</classPercent>
    </coverPageHeaderReportingPersonDetails>
    <items><item4><amountBeneficiallyOwned>See cover page</amountBeneficiallyOwned></item4></items>
  </formData>
</edgarSubmission>"""

ARK = """date,fund,company,ticker,cusip,shares,market value ($),weight (%)
09/29/2026,ARKK,TESLA INC,TSLA,88160R101,"2,133,265","$762,535,574.25",8.92%
09/29/2026,ARKK,CASH,,,"",,"0.1%"
"""

INSIDERS = """<html><body>
<table><tr><td>Owner</td><td>Filings</td><td>Transaction Date</td><td>Type of Owner</td></tr>
<tr><td>BUFFETT WARREN E</td><td>0000315090</td><td>2026-09-17</td><td>10 percent owner</td></tr>
<tr><td>BERKSHIRE HATHAWAY INC</td><td>0001067983</td><td>2026-09-17</td><td>10 percent owner</td></tr>
<tr><td>Lee Martin</td><td>0002028758</td><td>2025-10-02</td><td>officer: Chief Legal Officer</td></tr></table>
<table>
<tr><th>Acquistion or Disposition</th><th>Transaction Date</th><th>Deemed Execution Date</th><th>Reporting Owner</th>
<th>Form</th><th>Transaction Type</th><th>Direct or Indirect Ownership</th><th>Number of Securities Transacted</th>
<th>Number of Securities Owned</th><th>Line Number</th><th>Owner CIK</th><th>Security Name</th></tr>
<tr><td>A</td><td>2026-09-25</td><td></td><td>BUFFETT WARREN E</td><td>4</td><td>P-Purchase</td><td>I</td>
<td>313379</td><td>25206411</td><td>4</td><td></td><td>Class A Common Stock</td></tr>
<tr><td>A</td><td>2026-09-25</td><td></td><td>BERKSHIRE HATHAWAY INC</td><td>4</td><td>P-Purchase</td><td>I</td>
<td>313379</td><td>25206411</td><td>4</td><td></td><td>Class A Common Stock</td></tr>
<tr><td>D</td><td>2026-09-02</td><td></td><td>Lee Martin</td><td>4</td><td>S-Sale</td><td>D</td>
<td>1000</td><td>5000</td><td>1</td><td></td><td>Class A Common Stock</td></tr>
<tr><td>A</td><td>2026-03-01</td><td></td><td>Lee Martin</td><td>4</td><td>A-Award</td><td>D</td>
<td>2000</td><td>6000</td><td>1</td><td></td><td>Class A Common Stock</td></tr>
</table></body></html>"""


def test_form4_purchases_and_holdings_of_the_main_class():
    f = parse_form4(FORM4)
    assert f["ticker"] == "LEN" and f["issuer_cik"] == 920760
    assert [t["action"] for t in f["trades"]] == ["achat", "achat"]  # the grant (A) is not a market trade
    assert f["trades"][0]["price"] == 81.65
    assert f["shares"] == 24651340  # last figure of class A, not class A + class B


def test_schedule13_cover_page():
    s = parse_schedule13(SCHEDULE_13G)
    assert s["cusip"] == "401382106" and s["issuer_cik"] == 2039972
    assert s["shares"] == 24699825 and s["pct"] == 12.7
    assert s["event_date"] == "2026-03-31"


def test_ark_csv_skips_cash_and_footer():
    rows = parse_ark_csv(ARK)
    assert len(rows) == 1
    assert rows[0] == {"date": "2026-09-29", "fund": "ARKK", "cusip": "88160R101", "ticker": "TSLA",
                       "company": "TESLA INC", "shares": 2133265.0, "value_usd": 762535574.25}


def test_insider_table_keeps_market_trades_once():
    rows = parse_insider_table(INSIDERS, "LEN", 920760)
    assert [(r["owner"], r["action"]) for r in rows] == [("BUFFETT WARREN E", "achat"), ("Lee Martin", "vente")]
    assert rows[0]["role"] == "10 percent owner"
    assert rows[1]["owned_after"] == 5000


def test_congress_impossible_dates():
    assert fix_date("2026-12-26", "2026-02-09") == "2025-12-26"  # year typed wrong
    assert fix_date("2025-05-17", "2025-05-11") is None  # a year back would be 359 days: unknown
    assert fix_date("2026-01-10", "2026-02-09") == "2026-01-10"


def test_tickers_and_roles():
    assert _norm("BRK-B") == "BRK.B" and _norm("GOOG") == "GOOGL" and _norm("MOG/A") == "MOG.A"
    assert _norm("GRMN UN") is None and _norm("2618") is None
    assert _role("director, 10 percent owner, officer: COB and CEO") == "COB and CEO"
    assert _role(float("nan")) == "?"
