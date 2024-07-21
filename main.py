from fastapi import FastAPI, Request, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse, FileResponse
import os
import psycopg2
from psycopg2.extras import DictCursor
import json
from weasyprint import HTML
from jinja2 import Environment, FileSystemLoader
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import uuid


app = FastAPI()

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



TEMPLATES_DIR = "templates"
CSS_DIR = os.path.join("static", "css")
FONTS_DIR = os.path.join("static", "fonts")
IMAGES_DIR = os.path.join("static", "images")
OUTPUT_DIR = os.path.join("static", "output")


# Diccionario para mapear tipos de archivos a directorios
FILE_TYPE_DIR_MAP = {
    "template": TEMPLATES_DIR,
    "css_files": CSS_DIR,
    "font_files": FONTS_DIR,
    "images_files": IMAGES_DIR
}

os.makedirs(IMAGES_DIR, exist_ok=True)
os.makedirs(TEMPLATES_DIR, exist_ok=True)
os.makedirs(CSS_DIR, exist_ok=True)
os.makedirs(FONTS_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)



template_env = Environment(loader=FileSystemLoader(TEMPLATES_DIR))

# Configurar Jinja2
template_loader = FileSystemLoader(TEMPLATES_DIR)
template_env = Environment(loader=template_loader)


# Función para generar el documento en segundo plano
def generate_document_task(template_name: str, context: dict, output_path: str):
    template = template_env.get_template(f"{template_name}.html")
    html_content = template.render(context)
    base_url = os.path.abspath("static") + os.sep
    HTML(string=html_content, base_url=base_url).write_pdf(output_path)


@app.post("/generate")
async def generate_document(background_tasks: BackgroundTasks, request: Request):
    data = await request.json()
    template_name = data.get('template')
    context = data.get('context', {})

    if not template_name:
        raise HTTPException(status_code=400, detail="Template name is required")

    unique_id = uuid.uuid4()  # Generar un identificador único
    output_path = os.path.join(OUTPUT_DIR, f"{template_name}_{unique_id}.pdf")
    background_tasks.add_task(generate_document_task, template_name, context, output_path)

    return {"message": "Document generation started", "file_path": output_path}


@app.get("/download/{file_name}")
async def download_document(file_name: str):
    file_path = os.path.join(OUTPUT_DIR, file_name)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path, media_type='application/pdf', filename=file_name)


@app.post("/generate_request")
async def generate_request(request: Request):
    data = await request.json()
    template_name = data.get('template')
    context = data.get('context', {})

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO document_requests (template_name, context, status) VALUES (%s, %s, %s) RETURNING id",
        (template_name, json.dumps(context), 'pending')
    )
    request_id = cursor.fetchone()[0]
    conn.commit()
    cursor.close()
    conn.close()

    return JSONResponse(content={"request_id": request_id})


# Endpoint to upload files (unchanged)
@app.post("/upload")
async def upload_files(
        template: UploadFile = File(...),
        css_files: list[UploadFile] = File(...),
        font_files: list[UploadFile] = File(...),
        #images_files: list[UploadFile] = File(...)
):
    files = {
        "template": (template, TEMPLATES_DIR),
        "css_files": (css_files, CSS_DIR),
        "font_files": (font_files, FONTS_DIR),
        #"images_files": (images_files, IMAGES_DIR)
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


# Endpoint to generate document (unchanged)
@app.post("/generates")
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


    template = template_env.get_template(f"{template_name}.html")
    html_content = template.render(context)
    unique_id = uuid.uuid4()  # Generar un identificador único
    pdf_file_path = f"{template_name}_{unique_id}.pdf"


    base_url = os.path.abspath("static") + os.sep


    HTML(string=html_content, base_url=base_url).write_pdf(pdf_file_path)


    #for template in templates:
     #   directory = FILE_TYPE_DIR_MAP.get(template['file_type'])
      #  if directory:
       #     file_path = os.path.join(directory, template["name"])
        #    os.remove(file_path)

    cursor.close()
    conn.close()

    return FileResponse(pdf_file_path, media_type='application/pdf', filename=pdf_file_path)


def process_document_requests():
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=DictCursor)
    cursor.execute("SELECT * FROM document_requests WHERE status = 'pending'")
    requests = cursor.fetchall()

    for request in requests:
        template_name = request['template_name']
        context = request['context']

        cursor.execute("SELECT * FROM templates")
        templates = cursor.fetchall()

        for template in templates:
            directory = FILE_TYPE_DIR_MAP.get(template['file_type'])
            if directory:
                file_path = os.path.join(directory, template["name"])
                with open(file_path, "wb") as f:
                    f.write(template["file"])


        template = template_env.get_template(f"{template_name}.html")
        html_content = template.render(context)

        pdf_file_path = f"{request['id']}_{template_name}.pdf"


        base_url = os.path.abspath("static") + os.sep

        HTML(string=html_content, base_url=base_url).write_pdf(pdf_file_path)



        for template in templates:
            directory = FILE_TYPE_DIR_MAP.get(template['file_type'])
            if directory:
                file_path = os.path.join(directory, template["name"])
                os.remove(file_path)

        # Actualizar el estado de la solicitud
        cursor.execute(
            "UPDATE document_requests SET status = %s, updated_at = %s WHERE id = %s",
            ('completed', datetime.now(), request['id'])
        )

    conn.commit()
    cursor.close()
    conn.close()



scheduler = BackgroundScheduler()
scheduler.add_job(process_document_requests, CronTrigger(hour=10, minute=19))
scheduler.start()


import atexit

atexit.register(lambda: scheduler.shutdown())


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)




#Jmeter
