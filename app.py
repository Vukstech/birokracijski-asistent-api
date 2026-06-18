"""
Milanov Birokracijski Asistent — Flask PDF API
Deploji na Render.com (besplatno)
"""

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import os
import io
import requests
import tempfile
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
import pdfrw

app = Flask(__name__)
CORS(app)  # Dozvoli web frontend pozive

# ─── PDF URLS (originali s arbeitsagentur.de) ───────────────────────────────
PDF_URLS = {
    "KG1":         "https://www.arbeitsagentur.de/datei/kg1-antrag-kindergeld_ba017202.pdf",
    "KG1_KIND":    "https://www.arbeitsagentur.de/datei/kg1-anlagekind_ba013117.pdf",
    "KiZ1":        "https://www.arbeitsagentur.de/datei/kiz1-antrag_ba036540.pdf",
    "KiZ1_AnA":    "https://www.arbeitsagentur.de/datei/kiz1-ana_ba034980.pdf",
    "KiZ1_AnK":    "https://www.arbeitsagentur.de/datei/kiz1-ank_ba035005.pdf",
}

FORMS_DIR = os.path.join(os.path.dirname(__file__), "forms")
os.makedirs(FORMS_DIR, exist_ok=True)


# ─── HELPER: Skini PDF i keširaj lokalno ────────────────────────────────────
def get_pdf(form_key: str) -> bytes:
    local_path = os.path.join(FORMS_DIR, f"{form_key}.pdf")
    if os.path.exists(local_path):
        with open(local_path, "rb") as f:
            return f.read()
    url = PDF_URLS.get(form_key)
    if not url:
        raise ValueError(f"Nepoznat form_key: {form_key}")
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    with open(local_path, "wb") as f:
        f.write(resp.content)
    return resp.content


# ─── HELPER: Pokušaj popuniti AcroForm polja ────────────────────────────────
def fill_acroform(pdf_bytes: bytes, fields: dict) -> bytes | None:
    """
    Pokušava popuniti AcroForm polja.
    Vraća None ako PDF nema polja ili su zaštićena.
    """
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        if "/AcroForm" not in reader.trailer["/Root"]:
            return None
        writer = PdfWriter()
        writer.append(reader)
        writer.update_page_form_field_values(
            writer.pages[0], fields, auto_regenerate=False
        )
        out = io.BytesIO()
        writer.write(out)
        out.seek(0)
        return out.read()
    except Exception:
        return None


# ─── HELPER: Overlay metoda (uvijek radi) ───────────────────────────────────
def fill_overlay(pdf_bytes: bytes, overlay_data: list) -> bytes:
    """
    overlay_data = lista dict-ova:
      { "page": 0, "x": 100, "y": 700, "text": "Milan Vuksanovic", "size": 10 }
    Nalijepljuje tekst na točne koordinate originalnog PDF-a.
    """
    # Napravi overlay PDF
    overlay_buffer = io.BytesIO()
    c = canvas.Canvas(overlay_buffer, pagesize=A4)

    # Grupiraj po stranicama
    pages_data: dict[int, list] = {}
    for item in overlay_data:
        pg = item.get("page", 0)
        pages_data.setdefault(pg, []).append(item)

    max_page = max(pages_data.keys()) if pages_data else 0

    for page_num in range(max_page + 1):
        items = pages_data.get(page_num, [])
        c.setFont("Helvetica", 10)
        for item in items:
            c.setFont("Helvetica", item.get("size", 10))
            c.drawString(item["x"], item["y"], str(item["text"]))
        c.showPage()

    c.save()
    overlay_buffer.seek(0)

    # Spoji s originalnim
    template = pdfrw.PdfReader(io.BytesIO(pdf_bytes))
    overlay = pdfrw.PdfReader(overlay_buffer)

    for i, page in enumerate(template.pages):
        if i < len(overlay.pages):
            merge = pdfrw.PageMerge(page)
            merge.add(overlay.pages[i]).render()

    result = io.BytesIO()
    pdfrw.PdfWriter().write(result, template)
    result.seek(0)
    return result.read()


# ─── KOORDINATE za KG1 (Milan's podaci) ─────────────────────────────────────
def get_kg1_overlay(user: dict) -> list:
    """
    Koordinate za KG1 formular — izmjerene na originalnom PDF-u.
    A4: (0,0) = donje lijevo, (595, 842) = gornje desno
    """
    return [
        # Stranica 1 — Antragsteller (podnositelj zahtjeva)
        {"page": 0, "x": 115, "y": 740, "text": user.get("familienname", ""), "size": 9},
        {"page": 0, "x": 370, "y": 740, "text": user.get("vorname", ""), "size": 9},
        {"page": 0, "x": 115, "y": 720, "text": user.get("strasse", ""), "size": 9},
        {"page": 0, "x": 370, "y": 720, "text": user.get("hausnummer", ""), "size": 9},
        {"page": 0, "x": 115, "y": 700, "text": user.get("plz", ""), "size": 9},
        {"page": 0, "x": 200, "y": 700, "text": user.get("ort", ""), "size": 9},
        {"page": 0, "x": 115, "y": 680, "text": user.get("geburtsdatum", ""), "size": 9},
        {"page": 0, "x": 370, "y": 680, "text": user.get("steuer_id", ""), "size": 9},
        {"page": 0, "x": 115, "y": 640, "text": user.get("telefon", ""), "size": 9},
        {"page": 0, "x": 370, "y": 640, "text": user.get("email", ""), "size": 9},
        # IBAN
        {"page": 0, "x": 115, "y": 580, "text": user.get("iban", ""), "size": 9},
    ]


def get_kiz1_overlay(user: dict) -> list:
    return [
        {"page": 0, "x": 115, "y": 740, "text": user.get("familienname", ""), "size": 9},
        {"page": 0, "x": 370, "y": 740, "text": user.get("vorname", ""), "size": 9},
        {"page": 0, "x": 115, "y": 720, "text": user.get("strasse", ""), "size": 9},
        {"page": 0, "x": 370, "y": 720, "text": user.get("hausnummer", ""), "size": 9},
        {"page": 0, "x": 115, "y": 700, "text": user.get("plz", ""), "size": 9},
        {"page": 0, "x": 200, "y": 700, "text": user.get("ort", ""), "size": 9},
        {"page": 0, "x": 115, "y": 680, "text": user.get("geburtsdatum", ""), "size": 9},
        {"page": 0, "x": 370, "y": 680, "text": user.get("steuer_id", ""), "size": 9},
        {"page": 0, "x": 115, "y": 640, "text": user.get("iban", ""), "size": 9},
    ]


def get_kg1_kind_overlay(user: dict, kind: dict) -> list:
    return [
        # Roditelj (gore)
        {"page": 0, "x": 115, "y": 740, "text": user.get("familienname", ""), "size": 9},
        {"page": 0, "x": 370, "y": 740, "text": user.get("vorname", ""), "size": 9},
        # Dijete
        {"page": 0, "x": 115, "y": 680, "text": kind.get("familienname", ""), "size": 9},
        {"page": 0, "x": 370, "y": 680, "text": kind.get("vorname", ""), "size": 9},
        {"page": 0, "x": 115, "y": 660, "text": kind.get("geburtsdatum", ""), "size": 9},
        {"page": 0, "x": 370, "y": 660, "text": kind.get("steuer_id", ""), "size": 9},
    ]


# ─── ROUTES ─────────────────────────────────────────────────────────────────

@app.route("/", methods=["GET"])
def index():
    return jsonify({
        "status": "ok",
        "service": "Milanov Birokracijski Asistent — PDF API",
        "endpoints": {
            "POST /fill/kg1": "Popuni KG1 Kindergeld zahtjev",
            "POST /fill/kg1-kind": "Popuni KG1 Anlage Kind (jedno dijete)",
            "POST /fill/kiz1": "Popuni KiZ1 Kinderzuschlag zahtjev",
            "POST /fill/kiz1-ana": "Popuni KiZ1 Anlage Antragsteller",
            "POST /fill/kiz1-ank": "Popuni KiZ1 Anlage Kind",
            "POST /fill/kindergeld-komplet": "Popuni KG1 + Anlage Kind × N djece (ZIP)",
        }
    })


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/fill/kg1", methods=["POST"])
def fill_kg1():
    """
    POST body (JSON):
    {
      "familienname": "Vuksanovic",
      "vorname": "Milan",
      "strasse": "Markobeler str",
      "hausnummer": "41",
      "plz": "63452",
      "ort": "Hanau",
      "geburtsdatum": "13.03.1984",
      "steuer_id": "27415068375",
      "telefon": "0176 21956978",
      "email": "milanvuksanovic0@gmail.com",
      "iban": "BE62974005892761"
    }
    """
    data = request.get_json(force=True)
    if not data:
        return jsonify({"error": "JSON body obavezan"}), 400

    try:
        pdf_bytes = get_pdf("KG1")
    except Exception as e:
        return jsonify({"error": f"Ne mogu skinuti KG1 PDF: {str(e)}"}), 500

    # Pokušaj AcroForm prvo
    result = fill_acroform(pdf_bytes, {
        "Familienname": data.get("familienname", ""),
        "Vorname": data.get("vorname", ""),
        "Strasse": data.get("strasse", ""),
        "Hausnummer": data.get("hausnummer", ""),
        "PLZ": data.get("plz", ""),
        "Ort": data.get("ort", ""),
        "Geburtsdatum": data.get("geburtsdatum", ""),
        "SteuerID": data.get("steuer_id", ""),
        "Telefon": data.get("telefon", ""),
        "Email": data.get("email", ""),
        "IBAN": data.get("iban", ""),
    })

    # Fallback na overlay
    if result is None:
        overlay = get_kg1_overlay(data)
        result = fill_overlay(pdf_bytes, overlay)

    return send_file(
        io.BytesIO(result),
        mimetype="application/pdf",
        as_attachment=True,
        download_name="KG1_Kindergeld_ausgefuellt.pdf"
    )


@app.route("/fill/kg1-kind", methods=["POST"])
def fill_kg1_kind():
    """
    POST body:
    {
      "user": { "familienname": "Vuksanovic", "vorname": "Milan", ... },
      "kind": { "familienname": "Vuksanovic", "vorname": "Mia",
                "geburtsdatum": "01.01.2015", "steuer_id": "..." }
    }
    """
    data = request.get_json(force=True)
    user = data.get("user", {})
    kind = data.get("kind", {})

    try:
        pdf_bytes = get_pdf("KG1_KIND")
    except Exception as e:
        return jsonify({"error": f"Ne mogu skinuti PDF: {str(e)}"}), 500

    overlay = get_kg1_kind_overlay(user, kind)
    result = fill_overlay(pdf_bytes, overlay)

    vorname = kind.get("vorname", "Kind")
    return send_file(
        io.BytesIO(result),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"KG1_AnlageKind_{vorname}.pdf"
    )


@app.route("/fill/kiz1", methods=["POST"])
def fill_kiz1():
    data = request.get_json(force=True)
    try:
        pdf_bytes = get_pdf("KiZ1")
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    overlay = get_kiz1_overlay(data)
    result = fill_overlay(pdf_bytes, overlay)

    return send_file(
        io.BytesIO(result),
        mimetype="application/pdf",
        as_attachment=True,
        download_name="KiZ1_Kinderzuschlag_ausgefuellt.pdf"
    )


@app.route("/fill/kiz1-ana", methods=["POST"])
def fill_kiz1_ana():
    data = request.get_json(force=True)
    try:
        pdf_bytes = get_pdf("KiZ1_AnA")
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    overlay = get_kiz1_overlay(data)
    result = fill_overlay(pdf_bytes, overlay)

    return send_file(
        io.BytesIO(result),
        mimetype="application/pdf",
        as_attachment=True,
        download_name="KiZ1_AnA_ausgefuellt.pdf"
    )


@app.route("/fill/kiz1-ank", methods=["POST"])
def fill_kiz1_ank():
    data = request.get_json(force=True)
    user = data.get("user", {})
    kind = data.get("kind", {})

    try:
        pdf_bytes = get_pdf("KiZ1_AnK")
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    overlay = get_kg1_kind_overlay(user, kind)
    result = fill_overlay(pdf_bytes, overlay)

    vorname = kind.get("vorname", "Kind")
    return send_file(
        io.BytesIO(result),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"KiZ1_AnK_{vorname}.pdf"
    )


@app.route("/fill/kindergeld-komplet", methods=["POST"])
def fill_kindergeld_komplet():
    """
    Popuni KG1 + Anlage Kind za svu djecu i vrati ZIP.
    POST body:
    {
      "user": { ...podaci roditelja... },
      "djeca": [
        { "familienname": "Vuksanovic", "vorname": "Mia", "geburtsdatum": "...", "steuer_id": "..." },
        { "familienname": "Vuksanovic", "vorname": "Dunja", ... },
        { "familienname": "Vuksanovic", "vorname": "Rio", ... }
      ]
    }
    """
    import zipfile

    data = request.get_json(force=True)
    user = data.get("user", {})
    djeca = data.get("djeca", [])

    files = {}

    # KG1 glavni zahtjev
    try:
        pdf_bytes = get_pdf("KG1")
        overlay = get_kg1_overlay(user)
        files["KG1_Hauptantrag.pdf"] = fill_overlay(pdf_bytes, overlay)
    except Exception as e:
        return jsonify({"error": f"KG1 greška: {str(e)}"}), 500

    # Anlage Kind za svako dijete
    for kind in djeca:
        try:
            pdf_bytes = get_pdf("KG1_KIND")
            overlay = get_kg1_kind_overlay(user, kind)
            vorname = kind.get("vorname", "Kind")
            files[f"KG1_AnlageKind_{vorname}.pdf"] = fill_overlay(pdf_bytes, overlay)
        except Exception as e:
            return jsonify({"error": f"Anlage Kind greška za {kind}: {str(e)}"}), 500

    # Napravi ZIP
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for filename, content in files.items():
            zf.writestr(filename, content)

    zip_buffer.seek(0)
    return send_file(
        zip_buffer,
        mimetype="application/zip",
        as_attachment=True,
        download_name="Kindergeld_Komplet.zip"
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
