from io import BytesIO
from typing import Any, List
import zipfile
from fastapi import FastAPI, Form, UploadFile, File, Response
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pydicom import dcmread


class MeasurementsModel(BaseModel):
    measurements: list[Any]


app = FastAPI()

# Add CORS middleware to allow cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
def process_dicom_series(zip_bytes: bytes) -> List[Any]:
    """Обрабатывает ZIP-архив с DICOM файлами"""
    dicom_datasets = []

    with zipfile.ZipFile(BytesIO(zip_bytes)) as zip_file:
        dcm_files = [f for f in zip_file.namelist() if f.lower().endswith('.dcm')]

        if not dcm_files:
            raise ValueError("В архиве нет DICOM файлов")

        for file_name in dcm_files:
            with zip_file.open(file_name) as dcm_file:
                dicom_datasets.append(dcmread(dcm_file))
        print('dicom datasets', dicom_datasets)
    return dicom_datasets

@app.post("/generate_mpr")
async def generate_mpr(dicom_series: UploadFile = File(..., description="ZIP архив с DICOM серией"),
    measurements: str = Form(..., description="JSON данные с точками")):
    print("Got points:", measurements)
    zip_bytes = await dicom_series.read()
    dicom_datasets = process_dicom_series(zip_bytes)

    with open("abc.dcm", "rb") as f:
        dicom_bytes = f.read()

    # Возвращаем как сырые DICOM-данные
    return Response(
        content=dicom_bytes,
        media_type="application/dicom",
        headers={"Content-Disposition": 'attachment; filename="abc.dcm"'}
    )
