"""The bank's daily credit notification, ISO 20022 camt.054.001.08, as German banks send it."""
from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape

NS = "urn:iso:std:iso:20022:tech:xsd:camt.054.001.08"


def _amt(cents: int) -> str:
    return f"{cents // 100}.{cents % 100:02d}"


def write(path: Path, day, company: dict, entries) -> None:
    ntries = []
    for p in entries:
        ntries.append(f"""      <Ntry>
        <Amt Ccy="EUR">{_amt(p.amount_cents)}</Amt><CdtDbtInd>CRDT</CdtDbtInd><Sts><Cd>BOOK</Cd></Sts>
        <BookgDt><Dt>{day.isoformat()}</Dt></BookgDt><ValDt><Dt>{day.isoformat()}</Dt></ValDt>
        <AcctSvcrRef>{p.pid}</AcctSvcrRef>
        <NtryDtls><TxDtls>
          <Refs><EndToEndId>{escape(p.pid + '-E2E')}</EndToEndId></Refs>
          <AmtDtls><TxAmt><Amt Ccy="EUR">{_amt(p.amount_cents)}</Amt></TxAmt></AmtDtls>
          <RltdPties><Dbtr><Pty><Nm>{escape(p.debtor_name)}</Nm></Pty></Dbtr>
            <DbtrAcct><Id><IBAN>{p.debtor_iban}</IBAN></Id></DbtrAcct></RltdPties>
          <RmtInf><Ustrd>{escape(p.reference)}</Ustrd></RmtInf>
        </TxDtls></NtryDtls>
      </Ntry>""")
    path.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="{NS}">
  <BkToCstmrDbtCdtNtfctn>
    <GrpHdr><MsgId>CAMT054-{day.isoformat()}</MsgId><CreDtTm>{day.isoformat()}T18:00:00</CreDtTm></GrpHdr>
    <Ntfctn>
      <Id>N-{day.isoformat()}</Id>
      <Acct><Id><IBAN>{company['iban']}</IBAN></Id><Ownr><Nm>{escape(company['name'])}</Nm></Ownr></Acct>
{chr(10).join(ntries)}
    </Ntfctn>
  </BkToCstmrDbtCdtNtfctn>
</Document>
""", encoding="utf-8")
