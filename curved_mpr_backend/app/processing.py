from scipy.interpolate import splprep, splev, interpn
import pydicom
import numpy as np
from scipy.interpolate import splprep, splev
from scipy.interpolate import interpn
import SimpleITK as sitk
from .models import Series


def calculate_curve_length_3d(points):
    """
    Calculates the length of a 3D curve defined by a sequence of points.

    Args:
        points: A list of tuples or NumPy arrays, where each element represents
                a 3D point (x, y, z).

    Returns:
        The total length of the 3D curve.
    """
    if len(points) < 2:
        return 0.0  # A curve needs at least two points

    points_array = np.array(points)
    total_length = 0.0

    for i in range(len(points_array) - 1):
        p1 = points_array[i]
        p2 = points_array[i+1]

        # Calculate Euclidean distance between p1 and p2
        distance = np.linalg.norm(p2 - p1)
        total_length += distance

    return total_length


def curved_mpr(volume, control_points, resolution=1.0, thickness=5):
    control_points = np.array(control_points)

    tck, u = splprep(control_points.T, s=50)
    curve_length = calculate_curve_length_3d(control_points)
    num_points = int(np.ceil(curve_length * resolution))
    u_new = np.linspace(0, 1, num_points)
    curve_points = np.array(splev(u_new, tck)).T

    # Вычисляем первую и вторую производную
    der1 = np.array(splev(u_new, tck, der=1)).T
    der2 = np.array(splev(u_new, tck, der=2)).T
    # print(der1[0], der2[0], curve_points.shape,)

    reconstructed = np.zeros((num_points, thickness * 2 + 1))

    for i, (pos, tangent, curvature) in enumerate(zip(curve_points, der1, der2)):
        # print(i, (pos, tangent, curvature))
        tangent /= (np.linalg.norm(tangent) + 1e-6)

        # Нормаль = единичный вектор второго производного (направление изгиба)
        normal = curvature / (np.linalg.norm(curvature) + 1e-6)
        # print('norm: ', normal)
        binormal = np.cross(tangent, normal)
        # print('binorm: ', binormal)
        binormal[2] = abs(binormal[2])
        # print(binormal)

        binormal /= (np.linalg.norm(binormal) + 1e-6)
        # print('uncommon: ', binormal)
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


def transform_array(arr):
    return [0 if x == 0 else 1 for x in arr]

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



def physical_to_voxel(physical_point, spacing, origin, direction):
    """Преобразует физические координаты в воксельные индексы
    Физические координаты - """
    physical_point = np.array(physical_point)
    index_point = (np.linalg.inv(direction) @
                   (physical_point - origin)) / spacing
    return index_point

def extractor(series: Series):
    series_uid =  series.series_uid
    dicom_files = series.files

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



def reconstruction(path, coords, series: Series, shift=10):
    ex = extractor(series)
    result_datasets = []
    for i in range(-shift, shift+1):
        points = [physical_to_voxel(c, ex[0], ex[1], ex[2]) for c in coords]
        points = [[pt[2], pt[1], pt[0]] for pt in points]
        ds = pydicom.dcmread(path)

        std = np.std(points, axis=0)
        std = transform_array(std)
        for j in range(len(points)):
            points[j][0] += i*std[0]
            points[j][1] += i*std[1]
            points[j][2] += i*std[2]
        new_img = curved_mpr(ex[3], points, resolution=1.0, thickness=80)
        ni = (new_img-np.min(new_img))/(np.max(new_img)-np.min(new_img))
        ni = ni * np.max(ds.pixel_array)+500
        ni = ni.astype(np.int16)
        print(ds.Rows, ds.Columns, ni.shape)
        pydicom.pixels.set_pixel_data(ds, ni, photometric_interpretation='MONOCHROME2',
                                      bits_stored=16)
        ds.Rows, ds.Columns = ni.shape
        ds.PixelSpacing = [1, 1]
        ds.InstanceNumber = f'{i+shift}'
        ds.SeriesInstanceUID = 'curvedmprseries'
        ds.SeriesDescription = 'CMPR'

        # Сохрянять серию на диск для работы эндпоинта не обязательно
        # ds.save_as(f'abc{i+shift}.dcm', write_like_original=False)

        result_datasets.append(ds)
    return result_datasets

# Обрати внимание, что извлечение данных я вернул в reconstruction(), и
# теперь первым параметром там path - путь к базовому файлу.
# Также имя результирующего файла больше не переменная, они пронумерованы
# В таком виде, т.е. весь набор результирующих файлов, нужно
# резуультат загружать на вьюер
