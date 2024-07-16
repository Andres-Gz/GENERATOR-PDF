from fastapi import FastAPI, UploadFile, File, Request
from fastapi.responses import JSONResponse
import os
import psycopg2
from jinja2 import Environment, FileSystemLoader
from psycopg2.extras import DictCursor
from starlette.responses import FileResponse
from weasyprint import HTML

app = FastAPI()

# Configuración de la base de datos
DB_NAME = "postgres"
DB_USER = "postgres"
DB_PASSWORD = "AndresGZ12"
DB_HOST = "localhost"


def get_db_connection():
    conn = psycopg2.connect(
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST
    )
    return conn


# Directorios específicos
TEMPLATES_DIR = "templates"
CSS_DIR = os.path.join("static", "css")
FONTS_DIR = os.path.join("static", "fonts")

# Diccionario para mapear tipos de archivos a directorios
FILE_TYPE_DIR_MAP = {
    "template": TEMPLATES_DIR,
    "css_files": CSS_DIR,
    "font_files": FONTS_DIR
}

os.makedirs(TEMPLATES_DIR, exist_ok=True)
os.makedirs(CSS_DIR, exist_ok=True)
os.makedirs(FONTS_DIR, exist_ok=True)

template_env = Environment(loader=FileSystemLoader(TEMPLATES_DIR))


@app.post("/upload")
async def upload_files(
        template: UploadFile = File(...),
        css_files: list[UploadFile] = File(...),
        font_files: list[UploadFile] = File(...)
):
    files = {
        "template": (template, TEMPLATES_DIR),
        "css_files": (css_files, CSS_DIR),
        "font_files": (font_files, FONTS_DIR)
    }

    conn = get_db_connection()
    cursor = conn.cursor()

    for file_category, (file_list, directory) in files.items():
        if not isinstance(file_list, list):
            file_list = [file_list]

        for file in file_list:
            file_data = await file.read()
            cursor.execute(
                "INSERT INTO templates (name, file, file_type) VALUES (%s, %s, %s)",
                (file.filename, file_data, file_category)
            )

    conn.commit()
    cursor.close()
    conn.close()

    return JSONResponse(content={"message": "Files uploaded successfully"})


@app.post("/generate")
async def generate_document(request: Request):
    data = await request.json()
    template_name = data.get('template')
    context = data.get('context', {})

    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=DictCursor)

    cursor.execute("SELECT * FROM templates")
    templates = cursor.fetchall()

    for template in templates:
        directory = FILE_TYPE_DIR_MAP.get(template['file_type'])
        if directory:
            file_path = os.path.join(directory, template["name"])
            with open(file_path, "wb") as f:
                f.write(template["file"])

    # Renderizar la plantilla y generar el PDF
    template = template_env.get_template(f"{template_name}.html")
    html_content = template.render(context)

    pdf_file_path = f"{template_name}.pdf"

    # Ruta absoluta al directorio estático
    base_url = os.path.abspath("static") + os.sep

    # Generar el PDF
    HTML(string=html_content, base_url=base_url).write_pdf(pdf_file_path)

    # Después de generar el documento, eliminar los archivos temporales
    for template in templates:
        directory = FILE_TYPE_DIR_MAP.get(template['file_type'])
        if directory:
            file_path = os.path.join(directory, template["name"])
            os.remove(file_path)

    cursor.close()
    conn.close()

    return FileResponse(pdf_file_path, media_type='application/pdf', filename=pdf_file_path)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
