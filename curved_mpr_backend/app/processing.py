from pydicom import dcmread
import pydicom
from io import BytesIO
from typing import Any, List
import zipfile
from pydicom import dcmread
import numpy as np
from scipy.interpolate import splprep, splev
from scipy.interpolate import interpn
import SimpleITK as sitk

'''Поменять так, чтобы можно было отсортировать в extractor'''


# def process_dicom_series(zip_bytes: bytes) -> List[Any]:
#     """Обрабатывает ZIP-архив с DICOM файлами"""
#     dicom_datasets = []

#     with zipfile.ZipFile(BytesIO(zip_bytes)) as zip_file:
#         dcm_files = [f for f in zip_file.namelist()
#                      if f.lower().endswith('.dcm')]

#         if not dcm_files:
#             raise ValueError("There are no DICOM files in zip")

#         for file_name in dcm_files:
#             with zip_file.open(file_name) as dcm_file:
#                 dicom_datasets.append(dcmread(dcm_file))
#     return dicom_datasets


def change_spacing(image, new_spacing=[1., 1., 1.]):
    resample = sitk.ResampleImageFilter()
    resample.SetInterpolator(sitk.sitkLinear)
    resample.SetOutputDirection(image.GetDirection())
    resample.SetOutputOrigin(image.GetOrigin())
    new_spacing = np.array(new_spacing)
    resample.SetOutputSpacing(new_spacing)

    orig_size = np.array(image.GetSize(), dtype=np.int32)
    orig_spacing = np.array(image.GetSpacing())
    ratio = orig_spacing / new_spacing
    new_size = orig_size * (ratio)
    new_size = np.ceil(new_size).astype(np.int32)
    new_size = [int(s) for s in new_size]
    resample.SetSize(new_size)
    newimage = resample.Execute(image)

    return newimage


'''Можно обойтись без части со словарем и сортировки, а сразу перейти
с dcm-считке, но в общем случае такая сортировка может потребоваться'''


def extractor(series_dict):
    series_uid = max(series_dict, key=lambda k: len(series_dict[k]))
    dicom_files = series_dict[series_uid]

    # Сортируем файлы по InstanceNumber
    dicom_files.sort(key=lambda x: pydicom.dcmread(x).InstanceNumber)

    # Загружаем серию с помощью SimpleITK
    reader = sitk.ImageSeriesReader()
    reader.SetFileNames(dicom_files)
    image = reader.Execute()
    image = change_spacing(image)

    # Получаем метаданные изображения
    spacing = np.array(image.GetSpacing())
    origin = np.array(image.GetOrigin())
    direction = np.array(image.GetDirection()).reshape(3, 3)

    # Преобразуем SimpleITK изображение в numpy массив
    image_array = sitk.GetArrayFromImage(image)
    image_array = image_array.astype(float)
    return spacing, origin, direction, image_array


def physical_to_voxel(physical_point, spacing, origin, direction):
    """Преобразует физические координаты в воксельные индексы
    Физические координаты - """
    physical_point = np.array(physical_point)
    index_point = (np.linalg.inv(direction) @
                   (physical_point - origin)) / spacing
    return index_point


def curved_mpr(volume, control_points, resolution=1.0, thickness=5):
    control_points = np.array(control_points)

    tck, u = splprep(control_points.T, s=50)
    num_points = int(np.ceil(np.max(volume.shape) * resolution))
    u_new = np.linspace(0, 1, num_points)
    curve_points = np.array(splev(u_new, tck)).T

    # Вычисляем первую и вторую производную
    der1 = np.array(splev(u_new, tck, der=1)).T
    der2 = np.array(splev(u_new, tck, der=2)).T

    reconstructed = np.zeros((num_points, thickness * 2 + 1))

    for i, (pos, tangent, curvature) in enumerate(zip(curve_points, der1, der2)):
        tangent /= (np.linalg.norm(tangent) + 1e-6)

        # Нормаль = единичный вектор второго производного (направление изгиба)
        normal = curvature / (np.linalg.norm(curvature) + 1e-6)
        binormal = np.cross(tangent, normal)
        binormal[2] = abs(binormal[2])

        binormal /= (np.linalg.norm(binormal) + 1e-6)

        offsets = np.linspace(-thickness, thickness, thickness * 2 + 1)
        plane_points = pos[:, None] + binormal[:, None] * offsets

        values = interpn(
            (np.arange(volume.shape[0]), np.arange(
                volume.shape[1]), np.arange(volume.shape[2])),
            volume,
            plane_points.T,
            method='linear',
            bounds_error=False,
            fill_value=0
        )
        reconstructed[i, :] = values

    return reconstructed


# old
def reconstruction(new_img, ds, coords):
    ex = extractor()  # Коннектится с изображениями серии, по которой реконструируем
    volume = physical_to_voxel(coords, ex[0], ex[1], ex[2])
    new_img = curved_mpr(new_img, volume, thickness=80)
    ni = new_img*np.max(ds.pixel_array)/np.max(new_img)
    ni = (ni+2047-np.max(ni))-200
    ni = ni.astype(np.int16)
    pydicom.pixels.set_pixel_data(ds, ni, photometric_interpretation='MONOCHROME2',
                                  bits_stored=16)
    ds.Rows, ds.Columns = ni.shape
    ds.PixelSpacing = [1, 1]
    ds.InstanceNumber = '2'
    ds.SeriesInstanceUID = 'curvedmprseries'
    ds.SeriesDescription = 'CMPR'
    # ds.Modality = "OT"
    ds.save_as('abc.dcm', write_like_original=False)

# new
def reconstruct(series_dict, points):
    spacing, origin, direction, image_array = extractor(series_dict)

    volume = physical_to_voxel(points, spacing, origin, direction)
    new_img = curved_mpr(image_array, points, thickness=80)

def reconstruction(ds, coords, series_dict):
    # Коннектится с изображениями серии, по которой реконструируем
    ex = extractor(series_dict)
    points = [physical_to_voxel(c, ex[0], ex[1], ex[2]) for c in coords]
    new_img = curved_mpr(ex[3], points, thickness=80)
    ni = new_img*np.max(ds.pixel_array)/np.max(new_img)
    ni = (ni+3047-np.max(ni))
    ni = ni.astype(np.int16)
    pydicom.pixels.set_pixel_data(ds, ni, photometric_interpretation='MONOCHROME2',
                                  bits_stored=16)
    ds.Rows, ds.Columns = ni.shape
    ds.PixelSpacing = [1, 1]
    ds.InstanceNumber = '2'
    ds.SeriesInstanceUID = 'curvedmprseries'
    ds.SeriesDescription = 'CMPR'
    # ds.Modality = "OT"
    ds.save_as('abc3.dcm', write_like_original=False)
