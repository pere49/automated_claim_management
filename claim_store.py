import os
import json
import shutil
from datetime import datetime
from typing import List, Dict, Any, Optional

DEFAULT_CLAIMS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "claims_data"))

class ClaimItem:
    def __init__(
        self,
        month_year: str,
        individual_name: str,
        dir_path: str,
        claim_pdf: Optional[str] = None,
        statement_file: Optional[str] = None,
        receipt_files: List[str] = None,
        metadata: Dict[str, Any] = None
    ):
        self.month_year = month_year
        self.individual_name = individual_name
        self.dir_path = dir_path
        self.claim_pdf = claim_pdf
        self.statement_file = statement_file
        self.receipt_files = receipt_files or []
        self.metadata = metadata or {
            "month_year": month_year,
            "individual_name": individual_name,
            "project_name": "General Project",
            "claim_date": datetime.now().strftime("%Y-%m-%d"),
            "claimed_amount": 0.0,
            "verified_amount": 0.0,
            "status": "Pending",
            "verifier_notes": "",
            "verified_by": "",
            "updated_at": datetime.now().isoformat()
        }

    @property
    def status(self) -> str:
        return self.metadata.get("status", "Pending")

    @property
    def project_name(self) -> str:
        return self.metadata.get("project_name", "N/A")

    @property
    def claimed_amount(self) -> float:
        return float(self.metadata.get("claimed_amount", 0.0))

    @property
    def verified_amount(self) -> float:
        return float(self.metadata.get("verified_amount", 0.0))

    def save_metadata(self):
        self.metadata["updated_at"] = datetime.now().isoformat()
        meta_path = os.path.join(self.dir_path, "claim_meta.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(self.metadata, f, indent=2)

class ClaimStore:
    def __init__(self, root_dir: str = DEFAULT_CLAIMS_DIR):
        self.root_dir = os.path.abspath(root_dir)
        os.makedirs(self.root_dir, exist_ok=True)

    @staticmethod
    def _copy_claim_pdf_portrait(source_path: str, destination_path: str):
        """Store landscape claim pages with portrait display orientation."""
        import pymupdf as fitz

        source_doc = fitz.open(source_path)
        has_landscape_page = any(
            page.rect.width > page.rect.height for page in source_doc
        )

        if not has_landscape_page:
            source_doc.close()
            shutil.copy2(source_path, destination_path)
            return

        for page in source_doc:
            if page.rect.width > page.rect.height:
                page.set_rotation((page.rotation + 90) % 360)

        source_doc.save(destination_path)
        source_doc.close()

    def scan_claims(self) -> List[ClaimItem]:
        return self.scan_all()

    def scan_all(self) -> List[ClaimItem]:
        items = []
        if not os.path.exists(self.root_dir):
            return items

        # mm_yyyy folders
        for m_folder in sorted(os.listdir(self.root_dir), reverse=True):
            m_path = os.path.join(self.root_dir, m_folder)
            if not os.path.isdir(m_path):
                continue
            
            # individual_name folders
            for ind_folder in sorted(os.listdir(m_path)):
                ind_path = os.path.join(m_path, ind_folder)
                if not os.path.isdir(ind_path):
                    continue

                claim_pdf = None
                statement_file = None
                receipt_files = []
                meta = None

                files = sorted(os.listdir(ind_path))
                for fname in files:
                    fpath = os.path.join(ind_path, fname)
                    if not os.path.isfile(fpath):
                        continue

                    lower = fname.lower()
                    is_pdf = lower.endswith(".pdf")
                    is_image = any(lower.endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".webp"])

                    if lower == "claim_meta.json":
                        try:
                            with open(fpath, "r", encoding="utf-8") as f:
                                meta = json.load(f)
                        except Exception:
                            meta = None
                    elif lower.startswith("claim_form"):
                        # Files written by create_claim() use fixed, known prefixes.
                        # Match those directly so classification never depends on
                        # alphabetical processing order.
                        claim_pdf = fpath
                    elif lower.startswith("bank_statement"):
                        statement_file = fpath
                    elif lower.startswith("receipt_"):
                        receipt_files.append(fpath)
                    elif is_pdf or is_image:
                        # Fallback heuristic for files not created by create_claim
                        # (e.g. manually dropped into the folder).
                        if "statement" in lower or "bank" in lower:
                            statement_file = fpath
                        elif is_pdf and claim_pdf is None and "receipt" not in lower:
                            claim_pdf = fpath
                        else:
                            receipt_files.append(fpath)

                item = ClaimItem(
                    month_year=m_folder,
                    individual_name=ind_folder,
                    dir_path=ind_path,
                    claim_pdf=claim_pdf,
                    statement_file=statement_file,
                    receipt_files=receipt_files,
                    metadata=meta
                )
                items.append(item)

        return items

    def get_months(self) -> List[str]:
        if not os.path.exists(self.root_dir):
            return []
        months = [
            d for d in os.listdir(self.root_dir)
            if os.path.isdir(os.path.join(self.root_dir, d))
        ]
        return sorted(months, reverse=True)

    def create_claim(
        self,
        month_year: str,
        individual_name: str,
        project_name: str,
        claimed_amount: float,
        claim_date: str,
        claim_pdf_src: str,
        statement_src: Optional[str] = None,
        receipt_srcs: List[str] = None
    ) -> ClaimItem:
        # Normalize folder name
        clean_name = individual_name.strip().replace(" ", "_")
        target_dir = os.path.join(self.root_dir, month_year, clean_name)
        os.makedirs(target_dir, exist_ok=True)

        # Copy files
        claim_dest = os.path.join(target_dir, "claim_form.pdf")
        self._copy_claim_pdf_portrait(claim_pdf_src, claim_dest)

        stmt_dest = None
        if statement_src and os.path.exists(statement_src):
            ext = os.path.splitext(statement_src)[1]
            stmt_dest = os.path.join(target_dir, f"bank_statement{ext}")
            shutil.copy2(statement_src, stmt_dest)

        rcpt_dests = []
        if receipt_srcs:
            for idx, r_src in enumerate(receipt_srcs, start=1):
                if os.path.exists(r_src):
                    ext = os.path.splitext(r_src)[1]
                    dest = os.path.join(target_dir, f"receipt_{idx:02d}{ext}")
                    shutil.copy2(r_src, dest)
                    rcpt_dests.append(dest)

        meta = {
            "month_year": month_year,
            "individual_name": individual_name,
            "project_name": project_name,
            "claim_date": claim_date,
            "claimed_amount": float(claimed_amount),
            "verified_amount": float(claimed_amount),
            "status": "Pending",
            "verifier_notes": "",
            "verified_by": "",
            "updated_at": datetime.now().isoformat()
        }

        item = ClaimItem(
            month_year=month_year,
            individual_name=clean_name,
            dir_path=target_dir,
            claim_pdf=claim_dest,
            statement_file=stmt_dest,
            receipt_files=rcpt_dests,
            metadata=meta
        )
        item.save_metadata()
        return item

def generate_sample_data(store: ClaimStore):
    """Generates sample PDF claims and dummy receipt images if no data exists."""
    if len(store.scan_all()) > 0:
        return

    import pymupdf as fitz
    from PIL import Image, ImageDraw, ImageFont

    temp_dir = os.path.join(store.root_dir, "_temp_gen")
    os.makedirs(temp_dir, exist_ok=True)

    samples = [
        {
            "month": "09_2026",
            "name": "Sarah_Jenkins",
            "project": "Project Alpha - Logistics & Transport",
            "amount": 485.50,
            "status": "Pending",
            "items": [
                ("Taxi to Supplier Factory", "120.00"),
                ("Client Lunch Meeting", "85.50"),
                ("Hotel Accommodation 1 Night", "280.00")
            ]
        },
        {
            "month": "09_2026",
            "name": "David_Chen",
            "project": "Project Horizon - Cloud Infrastructure",
            "amount": 1290.00,
            "status": "Verified",
            "notes": "All server renewal receipts verified against bank statement.",
            "items": [
                ("AWS Cloud Servers Deposit", "850.00"),
                ("Domain & SSL Certificates", "140.00"),
                ("Dev Software Licenses", "300.00")
            ]
        },
        {
            "month": "08_2026",
            "name": "Maria_Garcia",
            "project": "Project Marketing - Q3 Campaign",
            "amount": 750.00,
            "status": "Needs Revision",
            "notes": "Receipt #2 missing vendor name stamp.",
            "items": [
                ("Print Flyers & Banners", "450.00"),
                ("Social Media Ads Boost", "300.00")
            ]
        }
    ]

    for idx, sample in enumerate(samples):
        # 1. Create PDF Claim Form
        pdf_path = os.path.join(temp_dir, f"claim_{idx}.pdf")
        doc = fitz.open()
        page = doc.new_page(width=595, height=842) # A4
        
        # Draw header
        page.insert_text(fitz.Point(50, 60), "COMPANY EXPENSE CLAIM FORM", fontsize=18, color=(0.1, 0.2, 0.6))
        page.insert_text(fitz.Point(50, 85), f"Claimant: {sample['name'].replace('_', ' ')}", fontsize=12)
        page.insert_text(fitz.Point(50, 105), f"Project: {sample['project']}", fontsize=12)
        page.insert_text(fitz.Point(50, 125), f"Date: 2026-09-10  |  Period: {sample['month']}", fontsize=12)
        
        # Draw table
        y = 170
        page.insert_text(fitz.Point(50, y), "Description", fontsize=11, color=(0.3, 0.3, 0.3))
        page.insert_text(fitz.Point(450, y), "Amount ($)", fontsize=11, color=(0.3, 0.3, 0.3))
        page.draw_line(fitz.Point(50, y+5), fitz.Point(540, y+5), color=(0.7, 0.7, 0.7))
        
        y += 25
        for desc, amt in sample["items"]:
            page.insert_text(fitz.Point(50, y), desc, fontsize=11)
            page.insert_text(fitz.Point(450, y), amt, fontsize=11)
            y += 20
        
        page.draw_line(fitz.Point(50, y+5), fitz.Point(540, y+5), color=(0.1, 0.2, 0.6), width=1.5)
        y += 25
        page.insert_text(fitz.Point(320, y), "TOTAL CLAIMED:", fontsize=12, color=(0.1, 0.2, 0.6))
        page.insert_text(fitz.Point(450, y), f"${sample['amount']:.2f}", fontsize=13, color=(0.1, 0.2, 0.6))
        
        page.insert_text(fitz.Point(50, 750), "Signature: __________________________   Date: 2026-09-10", fontsize=10)
        doc.save(pdf_path)
        doc.close()

        # 2. Create Bank Statement PDF
        stmt_path = os.path.join(temp_dir, f"statement_{idx}.pdf")
        doc_s = fitz.open()
        page_s = doc_s.new_page(width=595, height=842)
        page_s.insert_text(fitz.Point(50, 60), "GLOBAL BANK - MONTHLY STATEMENT", fontsize=16, color=(0.1, 0.4, 0.2))
        page_s.insert_text(fitz.Point(50, 85), f"Account Holder: {sample['name'].replace('_', ' ')}", fontsize=11)
        page_s.insert_text(fitz.Point(50, 105), f"Statement Period: {sample['month']}", fontsize=11)
        
        y_s = 150
        page_s.insert_text(fitz.Point(50, y_s), "Date       Transaction Details                     Amount ($)", fontsize=10)
        page_s.draw_line(fitz.Point(50, y_s+5), fitz.Point(540, y_s+5), color=(0.8, 0.8, 0.8))
        
        y_s += 25
        page_s.insert_text(fitz.Point(50, y_s), "2026-09-02  Salary Deposit                           +4,500.00", fontsize=10)
        y_s += 20
        for desc, amt in sample["items"]:
            page_s.insert_text(fitz.Point(50, y_s), f"2026-09-08  POS Merchant - {desc[:18]}         -{amt}", fontsize=10)
            y_s += 20
        
        doc_s.save(stmt_path)
        doc_s.close()

        # 3. Create Receipt Images (PNG)
        rcpt_paths = []
        for r_idx, (desc, amt) in enumerate(sample["items"], start=1):
            img = Image.new("RGB", (600, 800), color=(250, 248, 240))
            draw = ImageDraw.Draw(img)
            draw.rectangle([20, 20, 580, 780], outline=(180, 180, 180), width=2)
            draw.text((180, 50), "OFFICIAL RECEIPT", fill=(30, 30, 30))
            draw.text((50, 120), f"Merchant: Vendor {r_idx} Services", fill=(50, 50, 50))
            draw.text((50, 150), f"Item: {desc}", fill=(50, 50, 50))
            draw.text((50, 180), f"Date: 2026-09-08", fill=(50, 50, 50))
            draw.line([(50, 220), (550, 220)], fill=(200, 200, 200), width=1)
            draw.text((50, 250), f"TOTAL PAID: ${amt}", fill=(10, 120, 40))
            draw.text((50, 300), "[PAID BY CREDIT CARD - #### 4321]", fill=(100, 100, 100))
            
            r_path = os.path.join(temp_dir, f"rcpt_{idx}_{r_idx}.png")
            img.save(r_path)
            rcpt_paths.append(r_path)

        # Build claim item
        item = store.create_claim(
            month_year=sample["month"],
            individual_name=sample["name"],
            project_name=sample["project"],
            claimed_amount=sample["amount"],
            claim_date="2026-09-10",
            claim_pdf_src=pdf_path,
            statement_src=stmt_path,
            receipt_srcs=rcpt_paths
        )
        item.metadata["status"] = sample["status"]
        if "notes" in sample:
            item.metadata["verifier_notes"] = sample["notes"]
        item.save_metadata()

    # Clean up temp
    try:
        shutil.rmtree(temp_dir)
    except Exception:
        pass
