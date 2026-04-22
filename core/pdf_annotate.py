import fitz
from pathlib import Path
from typing import Dict, List, Tuple
import re
from io import BytesIO
from PIL import Image

def merge_pdfs(pdf_paths: List[Path], output_path: Path) -> Path:
    merged = fitz.open()

    for pdf_path in pdf_paths:
        try:
            doc = fitz.open(str(pdf_path))
            merged.insert_pdf(doc)
            doc.close()
        except Exception as e:
            print(f"[merge_pdfs] Impossible de lire {pdf_path.name}: {e}")

    merged.save(str(output_path), garbage=4, deflate=True)
    merged.close()

    return output_path

def is_page_number(text: str, page_num: int, total_pages: int) -> bool:
    text = text.strip() 
    if re.match(r'^\d{1,3}\s*/\s*\d{1,3}$', text):
        return True

    if re.match(r'^Page\s+\d{1,3}$', text, re.IGNORECASE):
        return True
    
    if re.match(r'^\d{1,3}$', text):
        try:
            num = int(text)
            if 1 <= num <= total_pages + 10:
                return True
        except:
            pass
    
    return False


def is_in_footer_or_header(rect: fitz.Rect, page_height: float, threshold: float = 50) -> bool:
    if rect.y0 > page_height - threshold:
        return True

    if rect.y1 < threshold:
        return True
    
    return False


def extract_search_terms(source_text: str, field_name: str = "") -> List[str]:
    if not source_text or source_text in ["Not found", "N/A", "", "0"]:
        return []
    
    search_terms = []
    
    cleaned = re.sub(r'^Page\s+\d+\s*[-–]\s*', '', source_text)
    
    if "Durée" in field_name or "Duration" in field_name:
        duration_patterns = [
            r'term of (\w+) \(\d+\) years?',
            r'period of (\w+) \(\d+\) years?',
            r'durée de (\w+) ans?',
            r'\d+ ans?',
            r'\d+ years?'
        ]
        
        for pattern in duration_patterns:
            matches = re.findall(pattern, cleaned, re.IGNORECASE)
            for match in matches:
                context_match = re.search(
                    rf'.{{0,50}}{re.escape(str(match))}.{{0,50}}',
                    source_text,
                    re.IGNORECASE
                )
                if context_match:
                    search_terms.append(context_match.group().strip())
        
        full_duration = re.findall(r'\w+ \(\d+\) years?', cleaned, re.IGNORECASE)
        search_terms.extend(full_duration)
    
    elif "Date signature" in field_name:
        if "DocuSign" in source_text or "Date:" in source_text:
            date_match = re.search(r'\d{1,2}[-/.]\w{3,}[-/.]\d{4}', cleaned)
            if date_match:
                search_terms.append(date_match.group())
            search_terms.append("DocuSigned by")
            search_terms.append("Date:")
    
    elif "Scope" in field_name:
        scope_terms = [
            "FM Demand Planning", "FM Supply Planning",
            "FM Demand", "FM Supply",
            "Demand Planning", "Supply Planning"
        ]
        for term in scope_terms:
            if term.lower() in cleaned.lower():
                search_terms.append(term)
    
    elif "Setup" in field_name:
        setup_keywords = ["Formation", "Onboarding", "Training", "Implementation"]
        for keyword in setup_keywords:
            if keyword.lower() in cleaned.lower():
                search_terms.append(keyword)
        amounts = re.findall(r'\d{1,3}(?:[,\.]\d{3})*\s*€', cleaned)
        search_terms.extend(amounts)
    
    elif "Ramp" in field_name or "Price" in field_name:
        rampup_terms = [
            "Year 1", "Year 2", "Année 1", "Année 2",
            "Phase 1", "Phase 2",
            "geste commercial", "commercial gesture"
        ]
        for term in rampup_terms:
            if term.lower() in cleaned.lower():
                search_terms.append(term)
    
    quotes = re.findall(r'["\']([^"\']{5,})["\']', cleaned)
    search_terms.extend(quotes)
    
    dates1 = re.findall(r'\d{1,2}[-\.]\w{3,}[-\.]\d{4}', cleaned)
    search_terms.extend(dates1)
    
    dates2 = re.findall(r'\d{1,2}/\d{1,2}/\d{4}', cleaned)
    search_terms.extend(dates2)
    
    amounts = re.findall(r'(\d{1,3}(?:[,\.]\d{3})+)\s*€', cleaned)
    search_terms.extend(amounts)
    
    key_phrases = re.findall(r'[:→]\s*([^|;]{10,100})', cleaned)
    search_terms.extend([p.strip() for p in key_phrases])
    
    cleaned_terms = []
    for term in search_terms:
        term = term.strip()
        if 3 <= len(term) <= 150:
            if not re.match(r'^\d{1,3}$', term):
                cleaned_terms.append(term)
    
    return list(set(cleaned_terms))


def fuzzy_search_in_page(
    page, 
    search_text: str, 
    field_name: str = "",
    page_num: int = 0,
    total_pages: int = 1
) -> List[fitz.Rect]:
    """
    Recherche floue avec filtrage des faux positifs (numéros de page, headers/footers)
    """
    instances = []
    
    exact = page.search_for(search_text)
    
    if exact:
        filtered = []
        page_height = page.rect.height
        
        for rect in exact:
            found_text = page.get_textbox(rect).strip()
            
            if is_page_number(found_text, page_num, total_pages):
                continue
            
            if "Date signature" not in field_name:
                if is_in_footer_or_header(rect, page_height):
                    continue
            
            if "TCV" in field_name or "€" in field_name:
                if re.match(r'^\d{1,3}$', found_text):
                    continue
            
            filtered.append(rect)
        
        return filtered
    
    cleaned_search = re.sub(r'[^\w\s]', '', search_text.lower())
    
    page_text = page.get_text()
    page_lines = page_text.split('\n')
    
    for line in page_lines:
        cleaned_line = re.sub(r'[^\w\s]', '', line.lower())
        
        if cleaned_search in cleaned_line:
            line_instances = page.search_for(line.strip())
            
            for rect in line_instances:
                found_text = page.get_textbox(rect).strip()
                
                if is_page_number(found_text, page_num, total_pages):
                    continue
                
                if "Date signature" not in field_name:
                    if is_in_footer_or_header(rect, page.rect.height):
                        continue
                
                instances.append(rect)
    
    return instances


def capture_screenshot_around_rect(page, rect: fitz.Rect, margin: int = 100) -> bytes:
    clip_rect = fitz.Rect(
        max(0, rect.x0 - margin),
        max(0, rect.y0 - margin),
        min(page.rect.width, rect.x1 + margin),
        min(page.rect.height, rect.y1 + margin)
    )
    pix = page.get_pixmap(clip=clip_rect, matrix=fitz.Matrix(3, 3))
    return pix.tobytes("png")


def extract_full_context_from_source(source_text: str, page, rect: fitz.Rect) -> str:
    context_rect = fitz.Rect(
        max(0, rect.x0 - 50),
        max(0, rect.y0 - 30),
        min(page.rect.width, rect.x1 + 50),
        min(page.rect.height, rect.y1 + 30)
    )
    
    context_text = page.get_textbox(context_rect).strip()
    
    if len(context_text) < 50:
        context_rect = fitz.Rect(
            max(0, rect.x0 - 100),
            max(0, rect.y0 - 60),
            min(page.rect.width, rect.x1 + 100),
            min(page.rect.height, rect.y1 + 60)
        )
        context_text = page.get_textbox(context_rect).strip()
    
    return context_text


def annotate_pdf_with_sources(
    pdf_path: str, 
    sources_dict: Dict, 
    output_path: str,
    generate_screenshots: bool = True
) -> Tuple[int, Dict[str, Tuple[bytes, str]]]:
    """
    Annote un PDF avec des rectangles colorés pour chaque source détectée
    
    Returns:
        (nombre d'annotations, {field_name: (screenshot_bytes, context_text)})
    """
    
    colors = {
        "Date signature": (1, 0, 0),
        "Scope": (0, 0.8, 0),
        "Price Ramp-up": (1, 0.5, 0),
        "Setup fees": (0, 0, 1),
        "Setup fees €": (0, 0, 1),
        "TCV": (1, 0, 1),
        "Durée": (0.5, 0, 0.5),
        "Durée du Contrat": (0.5, 0, 0.5),
        "SaaS Start Date": (0, 0.5, 0.5),
        "Ramp up price": (1, 0.5, 0),
    }
    
    doc = fitz.open(pdf_path)
    total_pages = len(doc)
    annotations_added = 0
    evidence = {}
    annotated_rects = set()
    
    for field_name, source_text in sources_dict.items():
        
        if not source_text or source_text in ["Not found", "N/A", "", "0"]:
            continue
        
        search_terms = extract_search_terms(source_text, field_name)
        
        if not search_terms:
            search_terms = [source_text.strip()]
        
        for search_text in search_terms:
            if len(search_text) < 3:
                continue
            
            for page_num in range(total_pages):
                page = doc[page_num]
                
                text_instances = fuzzy_search_in_page(
                    page, 
                    search_text, 
                    field_name, 
                    page_num, 
                    total_pages
                )
                
                for inst in text_instances:
                    rect_key = f"{page_num}-{inst.x0:.1f}-{inst.y0:.1f}"
                    if rect_key in annotated_rects:
                        continue
                    
                    annotated_rects.add(rect_key)
                    
                    color = colors.get(field_name, (0.5, 0.5, 0.5))
                    
                    highlight = page.add_highlight_annot(inst)
                    highlight.set_colors(stroke=color)
                    highlight.set_border(width=3)
                    highlight.update()
                    
                    annot = page.add_text_annot(
                        inst.tl,
                        f"{field_name}",
                        icon="Note"
                    )
                    annot.set_colors(stroke=color)
                    annot.update()
                    
                    annotations_added += 1
                    
                    if generate_screenshots and field_name not in evidence:
                        screenshot = capture_screenshot_around_rect(page, inst, margin=120)
                        context = extract_full_context_from_source(source_text, page, inst)
                        evidence[field_name] = (screenshot, context)
    
    if annotations_added > 0:
        add_legend(doc[0], colors, annotations_added)
    
    doc.save(output_path, garbage=4, deflate=True)
    doc.close()
    
    return annotations_added, evidence


def add_legend(page, colors: Dict, total_annotations: int):
    page_width = page.rect.width
    x_start = page_width - 200
    y_start = 30
    line_height = 15
    
    legend_rect = fitz.Rect(
        x_start - 10, 
        y_start - 5, 
        page_width - 10, 
        y_start + len(colors) * line_height + 25
    )
    
    page.draw_rect(legend_rect, color=(1, 1, 1), fill=(1, 1, 1), width=1)
    
    page.insert_text(
        (x_start, y_start + 10),
        "ANNOTATIONS",
        fontsize=10,
        color=(0, 0, 0),
        fontname="helv"
    )
    
    page.insert_text(
        (x_start, y_start + 22),
        f"Total: {total_annotations} éléments",
        fontsize=8,
        color=(0.3, 0.3, 0.3)
    )
    
    y = y_start + 35
    
    for field_name, color in colors.items():
        rect = fitz.Rect(x_start, y - 3, x_start + 12, y + 7)
        page.draw_rect(rect, color=color, fill=color, width=2)
        
        page.insert_text(
            (x_start + 18, y + 5),
            field_name,
            fontsize=7,
            color=(0, 0, 0)
        )
        
        y += line_height


def save_evidence_to_disk(
    evidence: Dict[str, Tuple[bytes, str]], 
    output_dir: Path, 
    client_name: str
):
    """
    Sauvegarde les preuves (screenshots + texte contexte) sur disque
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    for field_name, (img_bytes, context_text) in evidence.items():
        safe_field_name = re.sub(r'[^\w\s-]', '', field_name).strip().replace(' ', '_')
        
        img_path = output_dir / f"{client_name}_{safe_field_name}_proof.png"
        with open(img_path, 'wb') as f:
            f.write(img_bytes)
        
        txt_path = output_dir / f"{client_name}_{safe_field_name}_context.txt"
        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write(f"PREUVE POUR: {field_name}\n\n")
            f.write(f"Client: {client_name}\n\n")
            f.write(f"Contexte extrait du PDF:\n")
            f.write(context_text)