# Sources

What the jurisdiction-specific and Shari'ah-specific claims in this repository
rest on, so that a reader can check them rather than take them on trust. The
ledger itself needs none of this — it implements the brief as written. These
sources support AMBIGUITIES A9, A20 and A21, and §2 of the architecture
document.

The list is split deliberately. The first section is what I consulted and can
point at. The second is what I asserted from prior knowledge and have **not**
verified against a primary source; it is marked as such in place rather than
quietly mixed in, and nothing in it is load-bearing for a conclusion.

---

<a id="consulted"></a>

## Consulted

**Islamic finance regulation, UAE onshore**

- Central Bank of the UAE — Higher Shari'ah Authority.
  <https://www.centralbank.ae/en/our-operations/islamic-finance/shariah/>
  Used for: the HSA's existence, mandate and binding status over licensed
  Islamic financial institutions on the mainland.

- AAOIFI — announcement on the UAE's adoption of its standards.
  <https://aaoifi.com/announcement/aaoifi-welcomes-uaes-adoption-of-its-standards/?lang=en>
  Used for: AAOIFI Shari'ah Standards being mandatory for full-fledged Islamic
  banks, Islamic windows of conventional banks, and finance companies offering
  Shari'ah-compliant products, **with effect from 1 September 2018**. This is
  the specific claim in A20 and in §2 of the architecture document.

- CBUAE Rulebook — Standard re. Shari'ah Governance for Islamic Financial
  Institutions.
  <https://rulebook.centralbank.ae/en/rulebook/standard-re-shariah-governance-islamic-financial-institutions>
  Used for: the internal Shari'ah supervision requirement sitting alongside the
  HSA, i.e. that compliance is supervised at two levels rather than one.

- PwC Middle East — CBUAE Shari'ah Compliance Function standard.
  <https://www.pwc.com/m1/en/services/assurance/manage-risk-in-business/uae-central-bank-introduces-shariah-compliance-function-standard.html>
  Used for: the existence and timing of the Shari'ah Compliance Function
  standard and guidance note (issued April 2024, compliance required within a
  year). Secondary source — a law-firm/advisory summary, not the instrument.

**Islamic finance regulation, Abu Dhabi Global Market**

- ADGM — Islamic Finance Rulebook (IFR).
  <https://en.adgm.thomsonreuters.com/rulebook/islamic-finance-rulebook-ifr-ver08020125>
- ADGM — IFR 6.2, Shari'a Supervisory Board.
  <https://en.adgm.thomsonreuters.com/rulebook/ifr-62-sharia-supervisory-board-islamic-fund>
  Used for: ADGM being a separate regulatory perimeter under the FSRA with its
  own Islamic finance rulebook and its own Shari'a supervisory requirement.
  This is the basis for the claim that "a UAE-licensed bank" is at least two
  regulatory answers rather than one.

**Consumer protection**

- CBUAE Rulebook — Consumer Protection Regulation.
  <https://rulebook.centralbank.ae/en/rulebook/consumer-protection-regulation>
- CBUAE Rulebook — Consumer Protection Standards.
  <https://rulebook.centralbank.ae/en/rulebook/consumer-protection-standards>
  Used for: the Regulation being Circular No. 8/2020, issued 31 December 2020;
  the requirement that fees and charges be disclosed clearly, in advance, on a
  durable medium, in both English and Arabic. This is what makes a retroactive
  charge — for a day whose issued statement showed a credit balance — a
  consumer-protection exposure and not merely an operational annoyance.

**Shari'ah standards on debt and default**

- AAOIFI Shari'ah Standard No. 3 — Default in Payment by a Debtor (summary).
  <https://www.islamicfinance.com/2015/06/aaoifi-standard-number-three-default-payment-debtor/>
  Used for: the treatment of penalty clauses against a solvent debtor, and the
  *ta'widh* / *gharamah* distinction — proven actual loss may be recognised as
  income, a penalty may not and is directed to charity.
  Secondary source. Standards 3, 8 and 19 are the ones bearing on the overdraft
  fee analysis; **the standards themselves should be read before this argument
  is made in a room with a Shari'ah scholar in it.**

---

<a id="asserted"></a>

## Asserted from prior knowledge, not verified here

Listed so that the boundary is explicit. None of these carries a conclusion on
its own; where one appears in an argument, the argument also stands without it.

- **The AED and BHD pegs to the US dollar, and their rates.** A9 relies only on
  the qualitative claim that both currencies are pegged, so an AED/BHD cross is
  administratively determined rather than market-discovered. The specific peg
  rates are deliberately not quoted in any graded document, because I have not
  checked them against a central bank publication.
- **Kuwait moving from a dollar peg to a basket in 2007.** Used in A9 only as
  an illustration that a peg is policy rather than a constant. The argument
  does not depend on the example being this one.
- **The UAE business week moving to Monday–Friday.** Referenced in A21 only as
  a reason the ordinal "day" abstraction hides something, not as a rule the
  ledger implements.
- **AAOIFI's institutional location in Bahrain.** Considered and discarded as
  an explanation for the BHD account in the brief. The likely reason the second
  currency has three decimal places is that three decimal places break code
  written for two; a hidden Islamic-finance intent is the more interesting
  theory and the less probable one, and I am not building on it.

---

## Method

The Shari'ah analysis in A20 is applied reasoning, not a citation: the
structural claim — that a rate known in advance cannot be a Mudarabah profit
share, and that a charge recurring daily against a negative balance is
proportional to the duration of a debt regardless of being a flat amount —
follows from the standards above rather than being quoted from them. It is
offered as an engineer's reading of what the rules imply for a data model, and
it is the kind of conclusion that a bank's internal Shari'ah committee, not an
engineer, ultimately signs off. Flagging that boundary is part of the point:
the correct output of this analysis is not a verdict but the identification of
which decisions have to leave engineering entirely.
