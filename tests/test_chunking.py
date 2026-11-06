"""Chunk shapes from scripts/scraping/chunk.py: sub-labels, table dividers, split rows, PDF page titles."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "scraping"))
import chunk  # noqa: E402


def test_heading_ending_in_colon_stays_with_the_text_it_introduces():
    md = "## Step 1: Apply\n\n### What you need to do:\n\n- Apply for an HFE letter through the HDB Flat Portal.\n"
    (heading, blocks), = chunk.sections(md)
    assert heading == "Step 1: Apply"
    assert chunk.pack(blocks) == ["### What you need to do:\n\n- Apply for an HFE letter through the HDB Flat Portal."]


def test_ordinary_headings_still_start_sections():
    md = "## Eligibility conditions\n\nText one.\n\n## Amount\n\nText two.\n"
    assert [h for h, _ in chunk.sections(md)] == ["Eligibility conditions", "Amount"]


def test_bold_header_row_gets_its_missing_divider():
    table = "| **Household Type** | **Grant Amount** |\n| First-timer households | Up to $120,000 |"
    assert chunk.with_divider(table).split("\n")[1] == "| --- | --- |"


def test_headerless_table_is_left_as_it_is():
    # A divider would make the Citizenship row into column names for policy_synthesis.model_evidence.
    table = "| **Citizenship** | At least 1 applicant is a Singapore Citizen |\n| **Age** | At least 21 years old |"
    assert chunk.with_divider(table) == table


def test_a_cell_with_line_breaks_is_one_table_row():
    table = "| **Household** | Applicants aged 35 and above who are buying:\nA flat from HDB |\n| **Age** | 21 |"
    assert chunk.table_rows(table) == ["| **Household** | Applicants aged 35 and above who are buying:\nA flat from HDB |",
                                       "| **Age** | 21 |"]


def test_oversized_row_is_split_between_whole_sentences_repeating_its_label():
    sentence = "You must not own any private residential property in Singapore or overseas at application."
    row = chunk.row_text(["**Ownership**", " ".join([sentence] * 60)])
    table = "| Criteria | Details |\n|---|---|\n" + row
    parts = chunk.split_table(table)
    assert len(parts) > 1
    for part in parts:
        assert part.startswith("| Criteria | Details |\n|---|---|\n| **Ownership** | ")
        assert len(part.split()) <= chunk.TARGET_WORDS + 60
    body = " ".join(chunk.cells(p.split("\n")[2])[1] for p in parts)
    assert body == " ".join([sentence] * 60)  # every word kept, in order


def test_two_tables_never_share_a_chunk_and_a_caption_stays_with_its_table():
    blocks = ["Grant Amount Based on Household Type", "| **A** | **B** |\n| 1 | 2 |", "| **C** | **D** |\n| 3 | 4 |"]
    chunks = chunk.pack(blocks)
    assert len(chunks) == 2
    assert chunks[0].startswith("Grant Amount Based on Household Type\n\n| **A** | **B** |")


def test_pdf_page_gets_its_own_title_when_it_names_a_variant():
    root = "Enhanced CPF Housing Grant (EHG) amount for single"
    page = ("Enhanced CPF Housing Grant (EHG) amount for two or\nmore first-timer singles\n"
            "You may refer to the table below for the EHG amount.")
    assert chunk.pdf_page_title(page, root) == "Enhanced CPF Housing Grant (EHG) amount for two or more first-timer singles"


def test_pdf_title_joins_a_hyphen_wrap_and_keeps_the_document_title_when_equal():
    root = "Enhanced CPF Housing Grant (EHG) amount for first-timer households"
    page = "Enhanced CPF Housing Grant (EHG) amount for first-\ntimer households\nYou may refer to the table below."
    assert chunk.pdf_page_title(page, root) is None


def test_pdf_numbered_clauses_and_repeated_headers_keep_page_numbers():
    assert chunk.pdf_page_title("6 Housing Loan\nBuyers who are eligible for an HDB loan", "IMPORTANT NOTES ON OPTION TO PURCHASE") is None
    root = "TERMS AND CONDITIONS OF SALE AND PURCHASE OF AN HDB RESALE FLAT"
    assert chunk.pdf_page_title(root + "\n2 OPTION TO PURCHASE", root) is None


def test_pdf_sections_use_the_page_title_in_the_heading():
    md = ("## Page 3\n\nEnhanced CPF Housing Grant (EHG) amount for two or\nmore first-timer singles\n"
          "Not more than $1,500 $120,000\n")
    (heading, _), = chunk.sections(md, root="Enhanced CPF Housing Grant (EHG) amount for single")
    assert heading == "Enhanced CPF Housing Grant (EHG) amount for two or more first-timer singles > Page 3"
