from io import BytesIO
import io
import json
import os
import tempfile
import zipfile
from fastapi import FastAPI, Form, HTTPException, UploadFile, File, Response
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pydicom import dcmread, dcmwrite
import SimpleITK as sitk
import pydicom
from app.processing import change_spacing, physical_to_voxel, curved_mpr
import numpy as np
import uuid

app = FastAPI()

# Add CORS middleware to allow cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# class MeasurementModel(BaseModel):
#     points: list[list[float]]

def dataset_to_bytes(ds) -> bytes:
    buffer = BytesIO()
    dcmwrite(buffer, ds)
    buffer.seek(0)
    return buffer.getvalue()

@app.post("/reconstruct")
async def generate_mpr(file: UploadFile = File(...),
    measurements: str = Form(...)):

    # Парсим measurements
    try:
        measurements = json.loads(measurements)
    except json.JSONDecodeError:
        return HTTPException(status_code=400, detail="measurements must be valid JSON")

    # сохраняем zip
    if not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail=".zip file required")

    contents = await file.read()
    try:
        z = zipfile.ZipFile(io.BytesIO(contents), 'r')
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Bad zip file")

    with tempfile.TemporaryDirectory() as tmpdir:
        for zip_info in z.infolist():
            if zip_info.is_dir():
                continue
            zip_info.filename = os.path.basename(zip_info.filename)
        dcm_files_infolist = [zip_info for zip_info in z.infolist() if zip_info.filename.lower().endswith('.dcm')]

        z.extractall(tmpdir, dcm_files_infolist)

        reader = sitk.ImageSeriesReader()
        series_uids = reader.GetGDCMSeriesIDs(tmpdir)
        if not series_uids:
            raise HTTPException(status_code=400, detail="zip does not contain a valid DICOM series")
        if len(series_uids) > 1:
            raise HTTPException(status_code=400, detail="zip contains more than 1 DICOM series")
        series_uid = series_uids[0]

        series_file_names = reader.GetGDCMSeriesFileNames(tmpdir, series_uid)

        # ---------extractor-----------------
        reader.SetFileNames(series_file_names)
        image = reader.Execute()
        image = change_spacing(image)

        # Получаем метаданные изображения
        spacing = np.array(image.GetSpacing())
        origin = np.array(image.GetOrigin())
        direction = np.array(image.GetDirection()).reshape(3, 3)

        # Преобразуем SimpleITK изображение в numpy массив
        image_array = sitk.GetArrayFromImage(image)
        # image_array = image_array.astype(float)


        # ----ds-----
        ds = pydicom.dcmread(series_file_names[0])
        #---------reconstruct------------
        coords = [p for m in measurements for p in m['points']]
        points = [physical_to_voxel(c, spacing, origin, direction) for c in coords]
        points = [[pt[2], pt[1], pt[0]] for pt in points]
        new_img = curved_mpr(image_array, points, thickness=80)
        ni = new_img*np.max(ds.pixel_array)/np.max(new_img)
        ni = (ni+3547-np.max(ni))
        ni = ni.astype(np.int16)
        pydicom.pixels.set_pixel_data(ds, ni, photometric_interpretation='MONOCHROME2',
                                    bits_stored=16)
        ds.Rows, ds.Columns = ni.shape
        ds.PixelSpacing = [1, 1]
        ds.InstanceNumber = '2'
        # ds.SeriesInstanceUID = 'curvedmprseries'
        ds.SeriesInstanceUID = str(uuid.uuid4())
        ds.SeriesDescription = 'CMPR'
        # ds.Modality = "OT"
        ds.save_as('abc3.dcm')


        dicom_bytes = dataset_to_bytes(ds)

        return Response(
            content=dicom_bytes,
            media_type="application/dicom",
            headers={"Content-Disposition": 'attachment; filename="cmpr.dcm"'}
        )
