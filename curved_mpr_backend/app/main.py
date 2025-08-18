from io import BytesIO
import io
import json
from pathlib import Path
import zipfile
from fastapi import FastAPI, Form, HTTPException, UploadFile, File, Response
from fastapi.middleware.cors import CORSMiddleware
from pydicom import dcmread, dcmwrite
import SimpleITK as sitk
from .models import Series
from .processing import reconstruction

app = FastAPI(root_path="/api")

# Add CORS middleware to allow cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/hello")
def read_hello():
    return {"Hello": "World"}

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

    if not all([m.get('referenceSeriesUID') for m in measurements]):
        return HTTPException(status_code=400, detail="measurements does not belong to one series")

    series_uid_from_measurements = measurements[0].get('referenceSeriesUID')

    # проверяем, что файл действительно zip
    if not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail=".zip file required")

    # читаем файл и проверяем еще раз
    contents = await file.read()
    try:
        z = zipfile.ZipFile(io.BytesIO(contents), 'r')
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Bad zip file")

    target_extract_dir = Path('./data/' + series_uid_from_measurements)
    for file_info in z.infolist():
        if not file_info.is_dir():
            orig_name = Path(file_info.filename).name
            file_info.filename = orig_name
            z.extract(file_info, path=target_extract_dir)

    series_reader = sitk.ImageSeriesReader()
    try:
        series_uids = series_reader.GetGDCMSeriesIDs(target_extract_dir)
    except RuntimeError:
        raise HTTPException(status_code=400, detail="Ошибка чтения DICOM-файлов: возможно, папка пуста или содержит не-DICOM файлы")

    if len(series_uids) == 0:
        raise HTTPException(status_code=400, detail="Не найдено ни одной DICOM-серии в указанной папке")

    if len(series_uids) > 1:
        raise HTTPException(status_code=400, detail=f"Обнаружено {len(series_uids)} серий! Ожидалась 1 серия. UID: {series_uids}")

    series_uid_from_series = series_uids[0]

    if series_uid_from_measurements != series_uid_from_series:
        raise HTTPException(status_code=400, detail=f"Series uid из measurements не совпадает с series uid из самой серии")

    series_uid = series_uid_from_measurements

    dcm_files = list(series_reader.GetGDCMSeriesFileNames(target_extract_dir, series_uid_from_series))

    series = Series(series_uid=series_uid, files=dcm_files)

    points = [p for m in measurements for p in m['points']]

    sample_dcm_file = dcm_files[0]

    reconstruction_datasets = reconstruction(path=sample_dcm_file, coords=points, series=series)

    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for i, ds in enumerate(reconstruction_datasets):
            dicom_buffer = BytesIO()
            ds.save_as(dicom_buffer, write_like_original=False)
            dicom_buffer.seek(0)

            filename = f"abc{i}.dcm"
            zipf.writestr(filename, dicom_buffer.getvalue())

    zip_buffer.seek(0)
    series_uid = reconstruction_datasets[0].SeriesInstanceUID
    return Response(
        content=zip_buffer.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename={series_uid}.zip",
            "X-Series-Instance-UID": series_uid,
            "X-Number-Of-Instances": str(len(reconstruction_datasets))
        }
    )
