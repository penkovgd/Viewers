import { DicomMetadataStore, utils } from '@ohif/core';
import JSZip from 'jszip';

export default function getCommandsModule({ servicesManager, commandsManager, extensionManager }) {
  const { measurementService, uiNotificationService } = servicesManager.services;
  const actions = {
    sendMeasurments: async () => {
      const { filterTool } = utils.MeasurementFilters;
      const measurementData = measurementService.getMeasurements(filterTool('Probe'));
      console.log('Got measurments:', measurementData);

      const POINTS_REQUIRED = 4;
      if (measurementData.length < POINTS_REQUIRED) {
        // throw new Error(`At least ${POINTS_REQUIRED} points required`);
        uiNotificationService.show({
          title: 'Sending point failed:',
          message: `At least ${POINTS_REQUIRED} points required`,
          type: 'error',
        });
        console.error(`At least ${POINTS_REQUIRED} points required`);
        return;
      }

      // Проверяем, чтобы у всех measurements был одинаковый StudyUID и SeriesUID
      const studyUIDs = new Set(measurementData.map(m => m.referenceStudyUID));
      const seriesUIDs = new Set(measurementData.map(m => m.referenceSeriesUID));

      if (studyUIDs.size !== 1) {
        throw new Error(`Inconsistent referenceStudyUID values: ${[...studyUIDs].join(', ')}`);
      }
      if (seriesUIDs.size !== 1) {
        throw new Error(`Inconsistent referenceSeriesUID values: ${[...seriesUIDs].join(', ')}`);
      }

      const [StudyInstanceUID] = studyUIDs;
      const [SeriesInstanceUID] = seriesUIDs;

      const dataSource = extensionManager.getActiveDataSource()[0];
      const series = await dataSource.retrieve.series.metadata({ StudyInstanceUID });

      const wadoClient = dataSource.retrieve.getWadoDicomWebClient();
      const SeriesRetrieveURL = `${wadoClient.wadoURL}/studies/${StudyInstanceUID}/series/${SeriesInstanceUID}`;

      try {
        // Получаем zip
        uiNotificationService.show({
          title: 'Fetching zip',
          type: 'info',
        });
        const zipResponse = await fetch(SeriesRetrieveURL + '?accept=application/zip', {
          method: 'GET',
          headers: {
            Accept: 'application/zip',
          },
        });
        if (!zipResponse.ok) {
          throw new Error(`DICOM fetch error: ${zipResponse.status} ${zipResponse.statusText}`);
        }

        const zipBlob = await zipResponse.blob();

        const formData = new FormData();

        // Добавляем zip в тело запроса
        formData.append('file', zipBlob, 'series.zip');

        // Добавляем точки в тело запроса
        formData.append('measurements', JSON.stringify(measurementData));

        uiNotificationService.show({
          title: 'Points sent to the server',
          type: 'info',
        });
        const response = await fetch(`/api/reconstruct`, {
          method: 'POST',
          body: formData,
        });
        if (!response.ok) {
          throw new Error(`Backend error: ${response.status} ${response.statusText}`);
        }

        // Сохраняем реконструкцию
        const arrayBuffer = await response.arrayBuffer();
        const zip: JSZip = await JSZip.loadAsync(arrayBuffer);

        let loadedCount = 0;

        const uploadPromises: Promise<void>[] = [];

        zip.forEach((relativePath: string, zipEntry: JSZip.JSZipObject) => {
          if (zipEntry.dir) {
            return;
          }
          uploadPromises.push(
            zipEntry
              .async('arraybuffer')
              .then(fileBuffer => {
                return dataSource.store.dicom(fileBuffer).then(() => {
                  loadedCount++;
                  console.log(`File ${relativePath} loaded`);
                });
              })
              .catch(error => {
                console.error(`Failed to load ${relativePath}:`, error);
              })
          );
        });

        await Promise.all(uploadPromises);
        console.log(`Successfuly loaded ${loadedCount} DICOM files`);

        // await dataSource.store.dicom(arrayBuffer); // ничего не возвращает, к сожалению

        const promiseId = 'Dcm4chee:' + StudyInstanceUID; // пересмотреть
        dataSource.deleteStudyMetadataPromise(promiseId);
        const series = await dataSource.retrieve.series.metadata({ StudyInstanceUID });

        uiNotificationService.show({
          title: 'Curved mrp saved',
          type: 'info',
        });
      } catch (error) {
        console.error('Fetch operation failed:', error);
      }
    },
  };
  const definitions = {
    sendMeasurments: {
      commandFn: actions.sendMeasurments,
    },
  };
  return {
    actions,
    definitions,
    defaultContext: 'ROUTE:VIEWER',
  };
}
