"""
Milanov Birokracijski Asistent — Flask PDF API
Deploji na Render.com (besplatno)
Koordinate izmjerene iterativno na originalnim PDF-ovima.
"""

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import os
import io
import zipfile
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4

app = Flask(__name__)
CORS(app)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

PDF_LOCAL = {
    "KiZ1":     os.path.join(BASE_DIR, "zahtijev za kinder geld.pdf"),
    "KiZ1_AnK": os.path.join(BASE_DIR, "zahtijevza djecu.pdf"),
    "KiZ1_AnA": os.path.join(BASE_DIR, "za partnera.pdf"),
    "KG1":      os.path.join(BASE_DIR, "kg1-antrag-kindergeld.pdf"),
    "KG1_AnK":  os.path.join(BASE_DIR, "kg1-anlagekind kinders.pdf"),
}


def get_pdf(form_key: str) -> bytes:
    local_path = PDF_LOCAL.get(form_key)
    if not local_path:
        raise ValueError(f"Nepoznat form_key: {form_key}")
    if not os.path.exists(local_path):
        raise FileNotFoundError(f"PDF nije pronadjen: {local_path}")
    with open(local_path, "rb") as f:
        return f.read()


def fill_overlay(pdf_bytes: bytes, overlay_data: list, page_index: int = 0) -> bytes:
    """
    Nalijepljuje tekst na PDF stranicu na tačnim koordinatama.
    page_index = koja stranica se popunjava (0-based).
    A4: (0,0) = donje lijevo, (595, 842) = gornje desno.
    """
    overlay_buffer = io.BytesIO()
    c = canvas.Canvas(overlay_buffer, pagesize=A4)

    for _ in range(page_index):
        c.showPage()

    c.setFont("Helvetica", 9)
    for item in overlay_data:
        c.setFont("Helvetica", item.get("size", 9))
        c.drawString(item["x"], item["y"], str(item["text"]))
    c.showPage()
    c.save()
    overlay_buffer.seek(0)

    template_reader = PdfReader(io.BytesIO(pdf_bytes))
    overlay_reader = PdfReader(overlay_buffer)
    writer = PdfWriter()

    for i, page in enumerate(template_reader.pages):
        if i < len(overlay_reader.pages):
            page.merge_page(overlay_reader.pages[i])
        writer.add_page(page)

    result = io.BytesIO()
    writer.write(result)
    result.seek(0)
    return result.read()


# ─── KOORDINATE (izmjerene na originalnim PDF-ovima) ─────────────────────────

def get_kg1_overlay(user: dict) -> list:
    """KG1 Antrag auf Kindergeld — stranica 2 (page_index=1)"""
    return [
        {"x": 38,  "y": 572, "text": user.get("steuer_id", ""),    "size": 9},
        {"x": 22,  "y": 532, "text": user.get("familienname", ""), "size": 9},
        {"x": 22,  "y": 500, "text": user.get("vorname", ""),      "size": 9},
        {"x": 22,  "y": 468, "text": user.get("geburtsdatum", ""), "size": 9},
        {"x": 168, "y": 468, "text": user.get("geburtsort", ""),   "size": 9},
        {"x": 22,  "y": 432, "text": f"{user.get('strasse', '')} {user.get('hausnummer', '')}, {user.get('plz', '')} {user.get('ort', '')}", "size": 9},
        {"x": 22,  "y": 116, "text": user.get("iban", ""),         "size": 9},
    ]


def get_kg1_ank_overlay(user: dict, kind: dict) -> list:
    """KG1 Anlage Kind — stranica 1 (page_index=0)"""
    return [
        # Roditelj header (gore lijevo)
        {"x": 22,  "y": 800, "text": f"{user.get('familienname', '')} {user.get('vorname', '')}", "size": 9},
        # Dijete
        {"x": 38,  "y": 560, "text": kind.get("steuer_id", ""),       "size": 9},
        {"x": 22,  "y": 518, "text": kind.get("familienname", ""),     "size": 9},
        {"x": 22,  "y": 480, "text": kind.get("vorname", ""),          "size": 9},
        {"x": 22,  "y": 446, "text": kind.get("geburtsdatum", ""),     "size": 9},
    ]


def get_kiz1_overlay(user: dict) -> list:
    """KiZ1 Antrag auf Kinderzuschlag — stranica 2 (page_index=1)"""
    return [
        {"x": 22,  "y": 648, "text": f"{user.get('familienname', '')} {user.get('vorname', '')}", "size": 9},
        {"x": 785, "y": 648, "text": user.get("geburtsdatum", ""),   "size": 9},
        {"x": 22,  "y": 598, "text": f"{user.get('strasse', '')} {user.get('hausnummer', '')}, {user.get('plz', '')} {user.get('ort', '')}", "size": 9},
        {"x": 590, "y": 568, "text": user.get("telefon", ""),        "size": 9},
        {"x": 22,  "y": 270, "text": user.get("iban", ""),           "size": 9},
    ]


def get_kiz1_ank_overlay(user: dict, kind: dict) -> list:
    """KiZ1 Anlage Kind — stranica 1 (page_index=0)"""
    return [
        # Roditelj header
        {"x": 22,  "y": 810, "text": f"{user.get('familienname', '')} {user.get('vorname', '')}", "size": 9},
        # Dijete — Familienname, Vorname + Geburtsdatum u prvom redu sekcije 1
        {"x": 22,  "y": 718, "text": f"{kind.get('familienname', '')} {kind.get('vorname', '')}", "size": 9},
        {"x": 785, "y": 718, "text": kind.get("geburtsdatum", ""),   "size": 9},
    ]


# ─── ROUTES ──────────────────────────────────────────────────────────────────

@app.route("/", methods=["GET"])
def index():
    return jsonify({
        "status": "ok",
        "service": "Milanov Birokracijski Asistent — PDF API",
        "endpoints": {
            "POST /fill/kg1":                   "KG1 Kindergeld (podnosi se JEDNOM)",
            "POST /fill/kg1-kind":              "KG1 Anlage Kind",
            "POST /fill/kiz1":                  "KiZ1 Kinderzuschlag (svakih 6mj)",
            "POST /fill/kiz1-ank":              "KiZ1 Anlage Kind",
            "POST /fill/kindergeld-komplet":    "KG1 + KiZ1 + djeca ZIP (onboarding)",
            "POST /fill/kinderzuschlag-obnova": "KiZ1 + djeca ZIP (obnova 6mj)",
        }
    })


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/fill/kg1", methods=["POST"])
def fill_kg1():
    data = request.get_json(force=True)
    if not data:
        return jsonify({"error": "JSON body obavezan"}), 400
    try:
        pdf_bytes = get_pdf("KG1")
    except Exception as e:
        return jsonify({"error": f"Ne mogu otvoriti KG1 PDF: {str(e)}"}), 500

    result = fill_overlay(pdf_bytes, get_kg1_overlay(data), page_index=1)
    return send_file(io.BytesIO(result), mimetype="application/pdf",
                     as_attachment=True, download_name="KG1_Kindergeld.pdf")


@app.route("/fill/kg1-kind", methods=["POST"])
def fill_kg1_kind():
    data = request.get_json(force=True)
    user = data.get("user", {})
    kind = data.get("kind", {})
    try:
        pdf_bytes = get_pdf("KG1_AnK")
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    result = fill_overlay(pdf_bytes, get_kg1_ank_overlay(user, kind), page_index=0)
    return send_file(io.BytesIO(result), mimetype="application/pdf",
                     as_attachment=True,
                     download_name=f"KG1_AnlageKind_{kind.get('vorname', 'Kind')}.pdf")


@app.route("/fill/kiz1", methods=["POST"])
def fill_kiz1():
    data = request.get_json(force=True)
    try:
        pdf_bytes = get_pdf("KiZ1")
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    result = fill_overlay(pdf_bytes, get_kiz1_overlay(data), page_index=1)
    return send_file(io.BytesIO(result), mimetype="application/pdf",
                     as_attachment=True, download_name="KiZ1_Kinderzuschlag.pdf")


@app.route("/fill/kiz1-ank", methods=["POST"])
def fill_kiz1_ank():
    data = request.get_json(force=True)
    user = data.get("user", {})
    kind = data.get("kind", {})
    try:
        pdf_bytes = get_pdf("KiZ1_AnK")
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    result = fill_overlay(pdf_bytes, get_kiz1_ank_overlay(user, kind), page_index=0)
    return send_file(io.BytesIO(result), mimetype="application/pdf",
                     as_attachment=True,
                     download_name=f"KiZ1_AnK_{kind.get('vorname', 'Kind')}.pdf")


@app.route("/fill/kindergeld-komplet", methods=["POST"])
def fill_kindergeld_komplet():
    """
    ONBOARDING — podnosi se JEDNOM.
    ZIP: KG1 + KG1_AnK×djeca + KiZ1 + KiZ1_AnK×djeca

    POST body:
    {
      "user": {
        "familienname": "Vuksanovic", "vorname": "Milan",
        "strasse": "Markobeler str", "hausnummer": "41",
        "plz": "63452", "ort": "Hanau",
        "geburtsdatum": "13.03.1984", "geburtsort": "Hanau",
        "steuer_id": "27415068375",
        "telefon": "0176 21956978", "email": "milanvuksanovic0@gmail.com",
        "iban": "BE62974005892761"
      },
      "djeca": [
        { "familienname": "Vuksanovic", "vorname": "Mia",
          "geburtsdatum": "01.01.2015", "steuer_id": "" },
        ...
      ]
    }
    """
    data = request.get_json(force=True)
    user = data.get("user", {})
    djeca = data.get("djeca", [])
    files = {}

    try:
        pdf = get_pdf("KG1")
        files["KG1_Hauptantrag.pdf"] = fill_overlay(pdf, get_kg1_overlay(user), page_index=1)
    except Exception as e:
        return jsonify({"error": f"KG1 greška: {str(e)}"}), 500

    for kind in djeca:
        try:
            pdf = get_pdf("KG1_AnK")
            files[f"KG1_AnlageKind_{kind.get('vorname', 'Kind')}.pdf"] = \
                fill_overlay(pdf, get_kg1_ank_overlay(user, kind), page_index=0)
        except Exception as e:
            return jsonify({"error": f"KG1_AnK greška ({kind.get('vorname')}): {str(e)}"}), 500

    try:
        pdf = get_pdf("KiZ1")
        files["KiZ1_Hauptantrag.pdf"] = fill_overlay(pdf, get_kiz1_overlay(user), page_index=1)
    except Exception as e:
        return jsonify({"error": f"KiZ1 greška: {str(e)}"}), 500

    for kind in djeca:
        try:
            pdf = get_pdf("KiZ1_AnK")
            files[f"KiZ1_AnlageKind_{kind.get('vorname', 'Kind')}.pdf"] = \
                fill_overlay(pdf, get_kiz1_ank_overlay(user, kind), page_index=0)
        except Exception as e:
            return jsonify({"error": f"KiZ1_AnK greška ({kind.get('vorname')}): {str(e)}"}), 500

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for filename, content in files.items():
            zf.writestr(filename, content)
    zip_buffer.seek(0)

    return send_file(zip_buffer, mimetype="application/zip",
                     as_attachment=True,
                     download_name="Kindergeld_Komplet_Onboarding.zip")


@app.route("/fill/kinderzuschlag-obnova", methods=["POST"])
def fill_kinderzuschlag_obnova():
    """
    OBNOVA svakih 6 mjeseci — samo KiZ1.
    ZIP: KiZ1 + KiZ1_AnK×djeca
    """
    data = request.get_json(force=True)
    user = data.get("user", {})
    djeca = data.get("djeca", [])
    files = {}

    try:
        pdf = get_pdf("KiZ1")
        files["KiZ1_Hauptantrag.pdf"] = fill_overlay(pdf, get_kiz1_overlay(user), page_index=1)
    except Exception as e:
        return jsonify({"error": f"KiZ1 greška: {str(e)}"}), 500

    for kind in djeca:
        try:
            pdf = get_pdf("KiZ1_AnK")
            files[f"KiZ1_AnlageKind_{kind.get('vorname', 'Kind')}.pdf"] = \
                fill_overlay(pdf, get_kiz1_ank_overlay(user, kind), page_index=0)
        except Exception as e:
            return jsonify({"error": f"KiZ1_AnK greška ({kind.get('vorname')}): {str(e)}"}), 500

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for filename, content in files.items():
            zf.writestr(filename, content)
    zip_buffer.seek(0)

    return send_file(zip_buffer, mimetype="application/zip",
                     as_attachment=True, download_name="KiZ1_Obnova.zip")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
