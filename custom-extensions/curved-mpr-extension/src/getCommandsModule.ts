import { DicomMetadataStore, utils } from '@ohif/core';

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

      // const StudyInstanceUID = '1.3.12.2.1107.5.1.4.76270.30000024122810361969400000019';
      // const SeriesInstanceUID = '1.3.12.2.1107.5.1.4.76270.30000024122810150182600001696'; // малленкая серия (1 инстанс)
      // const SeriesInstanceUID = '1.3.12.2.1107.5.1.4.76270.30000024122810501260100009281'; // большая серия (800 инстансов)
      // const SeriesInstanceUID = '1.3.12.2.1107.5.8.15.133421.30000024122816392585900000071'; // MIP Range
      const dataSource = extensionManager.getActiveDataSource()[0];
      const series = await dataSource.retrieve.series.metadata({ StudyInstanceUID });

      const wadoClient = dataSource.retrieve.getWadoDicomWebClient();
      // const SeriesRetrieveURL = series.find(
      //   s => s.SeriesInstanceUID === SeriesInstanceUID
      // ).RetrieveURL;
      // console.log(SeriesRetrieveURL); // http://localhost:8080/dcm4chee-arc/aets/DCM4CHEE/rs/studies/1.3.12.2.1107.5.1.4.76270.30000024122810361969400000019/series/1.3.12.2.1107.5.1.4.76270.30000024122810501260100009281?accept=application/zip
      // const SeriesRetrieveURL = `${wadoClient.wadoURL}/studies/${StudyInstanceUID}/series/${SeriesInstanceUID}`;
      const SeriesRetrieveURL = `${window.location.origin}${wadoClient.wadoURL}/studies/${StudyInstanceUID}/series/${SeriesInstanceUID}`;

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

        // https://httpbin.org/post
        // http://127.0.0.1:8000/generate_mpr/
        uiNotificationService.show({
          title: 'Points sent to the server',
          type: 'info',
        });
        const response = await fetch(
          `${window.location.protocol}//${window.location.hostname}:8000/reconstruct`,
          {
            method: 'POST',
            body: formData,
          }
        );
        if (!response.ok) {
          throw new Error(`Backend error: ${response.status} ${response.statusText}`);
        }

        // Сохраняем .dcm от бекенда
        const arrayBuffer = await response.arrayBuffer();
        await dataSource.store.dicom(arrayBuffer); // ничего не возвращает, к сожалению

        const promiseId = 'DCM4CHEE:' + StudyInstanceUID; // пересмотреть
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
